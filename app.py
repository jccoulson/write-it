import logging
from flask import Flask, request, render_template, redirect, url_for, flash
from markupsafe import escape
from openai import AzureOpenAI
import os
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import datetime
import time
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import numpy as np
from detoxify import Detoxify

#basic logging setup
logger = logging.getLogger('writeit')
logger.setLevel(logging.ERROR)
#makes sure we are only taking error level and below
file_writer = logging.FileHandler('writeit.log')
file_writer.setLevel(logging.ERROR)
#putting date and time before message
format= logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_writer.setFormatter(format)
logger.addHandler(file_writer)

load_dotenv()

app = Flask(__name__)
#secret key for sessions
app.secret_key = os.getenv("SECRET_KEY")


#setting up mongoDB connection
try:
    client = MongoClient(os.getenv("AZURE_MONGO_CONNECTION_STRING"))
    db = client['writeit_db']  #the writeit-database
    users_collection = db.users
    #collection for daily essays
    essays_collection = db.essays
    #collection for daily prompts
    prompts_collection = db.prompts
    state_collection = db.state
except Exception as e:
    logger.error(f"Failed to setup MongoDB connection, error: {e}")
    raise

#login setup
login_manager = LoginManager()
try:
    login_manager.init_app(app)
    login_manager.login_view = 'login'
except Exception as e:
    logger.error(f"Failed to setup login manager, error: {e}")
    raise

#variables for api
api_key = os.getenv("AZURE_OAI_KEY")
azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
api_version = os.getenv("AZURE_OAI_VERSION")
try:
    client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=api_key,
        api_version=api_version
    )
except Exception as e:
    logger.error(f"Failed to init Azure Openai, error: {e}")

#route for the landing page
@app.route('/')
def landing_page():
    return render_template('landing_page.html')


#route for the difficulty selection page
@app.route('/difficulty')
@login_required
def difficulty():
    return render_template('difficulty.html')

#route for the read user's prompt from leaderboard
@app.route('/read',methods=['POST'])
def read():
    try: 
        if request.method == 'POST':
            mode = request.form['mode']
            user_id = request.form['user_id']
            username = request.form['username']
            essay_id = request.form['essay_id']
            #grab the text from essay collection based on user_id and mode
            essay=essays_collection.find_one({'user_id':ObjectId(user_id),'mode':mode, '_id':ObjectId(essay_id)}, {'text':1})
            
            if essay:
                essay = escape(essay['text']) #remove any html tags user added just in case of malicious actors
                #send the text and username
                return render_template('read.html', essay=essay, username=username, mode=mode)
            else:
                raise ValueError("Essay not found in database")
        else:
            return redirect('/rankings')
    except Exception as e:
        logger.error(f"Could not get user essay, error: {e}")
        return render_template('landing_page.html', error=str(e))


@app.route('/temp')
def temp():
    return render_template('temp.html')

#currently is rankings from all time, take out the essay_id_list when we want to do current rankings and uncomment the essay clear on prompt generation
#route for the rankings  page
@app.route('/rankings')
def rankings():
    try:
        #get top 10 scores, create a list that holds highest to lowest(0th element highest score)
        top_normal= list(essays_collection.find({'mode': 'normal'}, {'_id': 1, 'user_id': 1, 'score': 1, 'text': 1,"mode":1}).sort('score', -1).limit(10))
        top_challenge = list(essays_collection.find({'mode': 'challenge'}, {'_id': 1, 'user_id': 1, 'score': 1, 'text': 1,"mode":1}).sort('score', -1).limit(10))
        top_creative = list(essays_collection.find({'mode': 'creative'}, {'_id': 1, 'user_id': 1, 'score': 1, 'text': 1,"mode":1}).sort('score', -1).limit(10))
        
        #nested function for repetition and readability
        def get_name_score(top_list):
            essay_id_list = []
            score_list = []
            name_list = []
            userid_list = []
            mode_list = []
            #grab scores and user_id
            for essay in top_list:
                user_id= essay['user_id'] 
                top_name=users_collection.find_one({'_id':ObjectId(user_id)}, {"username":1,"mode":1})
                name_list.append(top_name['username'])
                score_list.append(essay['score'])
                userid_list.append(essay['user_id'])
                mode_list.append(essay['mode'])
                essay_id_list.append(essay['_id'])
            return zip(score_list,name_list,userid_list,mode_list, essay_id_list)
        
        normal_zip = get_name_score(top_normal)
        challenge_zip = get_name_score(top_challenge)
        creative_zip = get_name_score(top_creative)

        return render_template('rankings.html', top_normal=normal_zip,top_challenge=challenge_zip, top_creative=creative_zip)
    except Exception as e:
        logger.error(f"Could not retrieve rankings: {e}")
        return render_template('landing_page.html', error=str(e))

#taking a text as param, using Azure openAI API, embedds it
def generate_embeddings(text):
    response = client.embeddings.create(input=text, model='text-embedding-ada-002')
    embeddings = response.data[0].embedding
    return embeddings

#ATTENTION: ONLY TO BE CALLED ONCE AT START OF APP.PY
def create_similarity_index(collection_name):
    #this creates indexing for vector search to properly work
    db.command({
        #creates the indexes in the param collection name
        'createIndexes': collection_name,
        'indexes': [
            {
                'name': 'VectorSearchIndex',
                'key': {
                    "contentVector": "cosmosSearch"
                },
                'cosmosSearchOptions': {
                    'kind': 'vector-ivf',
                    'numLists': 1,
                    'similarity': 'COS', #utilizing cosine similarity
                    'dimensions': 1536  #dimensions too high = large runtime, too low = loss of information
                }
            }
        ]
    })

#vector searches on a specific vectorized prompt, default is 3 closest prompts, but generally we use 5
def vector_search(collection_name, query, num_results=3):
    #based on our collection name(prompts)
    collection = db[collection_name]
    #generate embeddings for current prompt
    query_embedding = generate_embeddings(query)    
    pipeline = [
        {
            '$search': {
                #searching for the k-nearest results that are similar to vector query embeddings, looks for embeddings in the contentVector field
                "cosmosSearch": {
                    "vector": query_embedding,
                    "path": "contentVector",
                    "k": num_results
                },
                "returnStoredSource": True }},
        {'$project': { 'similarityScore': { '$meta': 'searchScore' }, 'document' : '$$ROOT' } }
    ]
    results = collection.aggregate(pipeline)
    return results

#a reverse RAG pipeline for a unique prompt generation - takes in prompt and prompt type as params, then vector searches 5 closest essays to it,
#then with a new message based on type, creates a new prompt that is different than the 5 closest to it
def rag_with_vector_search(essay_prompt, type):
    #grab the 5 closest essays to our param essay using vector search
    results = vector_search("prompts", essay_prompt, num_results=5)

    #adds the 5 essays to a one big string
    essay_list = ""
    for i,result in enumerate(results):
        essay_list = essay_list + "\n" + result['document']['prompt'] + "\n"
    
    #based on type, generate a specific system message for new prompt
    type_message = ""
    if type == "normal":
        type_message = """Make a normal, realistic prompt that is not too fantastical, the new prompt should be low on mysticism content. """
    elif type == "challenge":
        type_message = """Make a prompt that inlcudes a specific structural limitation, make sure that the new challenge you create is different than any of the other prompts. Make the challenge possible within the boundaries of writing on our website and make sure only one challenge is instructed for the prompt. """
    else:
        type_message = """Make a prompt that is creative and fantastical, the new prompt doesn't have to be realstic, but use understandable words to explain it. """
    
    #append the type specific instructions with general instructions
    system_prompt = type_message+"""The newly generated prompt should ONLY 3-4 sentences long. The newly generated prompt content MUST be different than the following prompts BUT structurally similar to the individual prompts:\n"""
    
    #append both final instructions with the 5 most similar essays
    formatted_prompt = ""
    formatted_prompt = system_prompt + essay_list

    messages = [
        {"role": "system", "content": formatted_prompt}
    ]
    #create and return newly created prompt based on reverse RAG
    completion = client.chat.completions.create(messages=messages, model='gpt-4')
    return completion.choices[0].message.content


#generate the writing prompts, should be called once per day
def helper_generate_prompts():
    try:
        #delete all of essays_collection uncomment if we want only daily leaderboards
        #essays_collection.delete_many({})

        list_of_prompts = []

        #for code simplicity call for nested function
        def generate_prompt(system_message):
            messages_array = [
            {"role": "system", "content": system_message},
            ]

            response = client.chat.completions.create(
                model="gpt-4",
                max_tokens=200,
                messages=messages_array
            )
            return response.choices[0].message.content
        
        def generate_system_message(type):
            #create a list of all existing prompts
            existing_prompts = list(prompts_collection.find({"type": type}, {"prompt": 1, "_id": 0}))
            existing_prompts_text = "\nPrompt:\n".join([item["prompt"] for item in existing_prompts])
            if type == "normal":
                #### Generate Normal Prompt ####
                system_message = """Generate minimum 3 sentence, maximum 4 sentence writing prompt that will help a user as a creative excersise, leave it slightly open ended. 
                Do be specifically prompting them, just set an environment for them to build on. 
                Don't really lead the user and don't ask them questions/give specific direction. 
                Don't say anything meta about prompting them, just the setting. 
                The prompt has to be a story/settings description, no meta talk, no saying words like write this or do this, etc

                Make sure that the newly generated prompt is not similar to any of these prompts.
                {existing_prompts_text}
                """
            elif type == "challenge":
                #### Generate Challenge Prompt ####
                system_message = """Generate minimum 3 sentence, maximum 4 sentence writing prompt that will help a user as a creative excersise, leave open ended. 
                This prompt's purpose is to have a syntactic/grammatic challenge of some kind.
                An example of challenge is: do not use any verb more than once in the whole writing. The challenge should be something like this, be creative.
                Don't really lead the user in the setting of the prompt, only in the challenge part. 
                Don't say anything meta about prompting them besides the challenge, just the setting. 
                The prompt has to be a story/settings description and challenge, no saying words like write this or do this, etc
                We already gave them a prompt for a normal piece of writing and creative piece of writing, the purpose of this is to be the challenge mode prompt.
                
                Make sure that the newly generated prompt is not similar to any of these prompts.
                {existing_prompts_text}
                """
            else:
                #### Generate Creative Prompt ####
                system_message = """Generate minimum 3 sentence, maximum 4 sentence writing prompt that will help a user as a creative excersise, leave open ended. 
                Do be specifically prompting them, just set an environment for them to build on. 
                Don't really lead the user and don't ask them questions/give specific direction. 
                Don't say anything meta about prompting them, just the setting. 
                The prompt has to be a story/settings description, no meta talk, no saying words like write this or do this, etc
                This prompt is extremely creative/wacky/out there. 
                We already gave them a prompt for a normal piece of writing, this is the creative prompt so make it accordingly.
                
                Make sure that the newly generated prompt is not similar to any of these prompts.
                {existing_prompts_text}
                """
            return system_message
    
        #generate system message for each type
        normal_system_message = generate_system_message("normal")
        challenge_system_message = generate_system_message("challenge")
        creative_system_message = generate_system_message("creative")

        #creating a dictionary of prompt types with their system message stored
        prompt_types = {"normal": normal_system_message, "creative": creative_system_message, "challenge": challenge_system_message}

        #generates prompt for all types
        for prompt_type, system_message in prompt_types.items():
            new_prompt = generate_prompt(system_message) #initial prompt generated from database queries
            new_prompt = rag_with_vector_search(new_prompt, prompt_type) #perform vector search for k-closest closest similarities, then create new prompt unlike them
            list_of_prompts.append({"type": prompt_type, "prompt": new_prompt}) #appends to list
        
        print("LIST OF PROMPTS COMPLETED:\n",list_of_prompts)
        prompts_collection.update_many({}, {"$set": {"active": False}})  #set all old prompts to not active
        for prompt in list_of_prompts:
            content_vector = generate_embeddings(prompt["prompt"]) #embedds the new prompts prior to storing in database
            prompts_collection.insert_one({
                "type": prompt["type"],
                "prompt": prompt["prompt"],
                "date": datetime.datetime.now(),
                "active": True,
                "contentVector":content_vector #vectorized text
            })

        return list_of_prompts
    except Exception as e:
        logger.error(f"Error during prompt generation: {e}")
        raise



def find_prompt(mode, current_prompts):
    for item in current_prompts:
        if item["type"] == mode:
            return item["prompt"]

@app.route('/prompt', methods=['POST','GET'])
@login_required
def prompt():
    try:
        state = state_collection.find_one({})
        #check if its been a day since someone has last been on page to generate new prompt
        cur_time = datetime.datetime.now()
        time_elapsed = cur_time - datetime.timedelta(hours=24) #24 hours have elapsed
        current_prompts = ""
        if state and state['last_gen_time'] < time_elapsed:
            current_prompts = helper_generate_prompts()
            state_collection.update_one({}, {"$set": {"current_prompts": current_prompts, "last_gen_time": cur_time}})
        else:
            current_prompts = state['current_prompts']
     
        ### post check for development ###
        if request.method == 'POST':
            mode = request.form['mode']
            if mode == 'normal':
                return render_template('prompt.html',response_text=find_prompt(mode, current_prompts), current_mode = mode) #pass difficulty to prompt page for later storage
            elif mode == 'creative':
                return render_template('prompt.html',response_text=find_prompt(mode, current_prompts), current_mode = mode)
            elif mode == 'challenge':
                return render_template('prompt.html',response_text=find_prompt(mode, current_prompts), current_mode = mode)
        else:
            return redirect('/difficulty')
    except Exception as e:
        logger.error(f"Error handling prompt generation or display: {e}")
        return render_template('landing_page.html', error=str(e))
   

def check_toxicity(text):
    #var to gold if exception on Detoxift
    error_needs_review = False
    try:
        results = Detoxify('original').predict(text)
    except Exception as e:
        logger.error(f"Error with Detoxify model: {e}")
        #just go to gpt check for toxicity if model fails
        error_needs_review = True 

    try:
        #adjust threshold of toxicity if needed
        #there are multiple types such as toxicity, obscene, threat, etc
        needs_review = any(value >= 0.7 for value in results.values())

        #if it needs review because greater than trheshold, send it to gpt for double layer
        if needs_review or error_needs_review:
            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version
            )
            system_message = f"""A user has written an essay as input for my web application. I will show your their content please judge if it is appropriate, swearing and graphic stories are allowed, but nothing considered extremely inappropriate or if they just entered hateful or extremely toxic content. Only answer with a number 0 if the content is acceptable to these guidlines, 1 if they are not. No other content except the number."""

            messages_array = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ]

            response = client.chat.completions.create(
                model="gpt-4",
                max_tokens=10,
                messages=messages_array
            )
            toxicity_analysis = response.choices[0].message.content
            #toxicity or not will be based on gpt response
            if toxicity_analysis == "0":
                return False
            else:
                return True

        return False
    except Exception as e:
        logger.error(f"Error during toxicity check with OpenAI: {e}")
        return True #assume toxic if all fails, to be safe

    

#page that uses openai to analyze the submitted essay
@app.route('/analysis', methods=['POST'])
@login_required
def analysis():
    #empty list incase got to page wtihout post request, can probably remove
    response_list = [""]*3
    text_parts = [""]*2
    analysis_parts = [""]*2
    text_parts2 = [""]*2
    analysis_parts2 = [""]*2


    if request.method == 'POST':
        try:
            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version
            )
        except Exception as e:
            logger.error(f"Failed to init Azure Openai, error: {e}")
            return render_template('landing_page.html', error=str(e))

        #get form data from submission of essay
        input_essay = request.form['inputEssay']
        mode = request.form['mode']

        #TODO eventually redirect to page to tell them their content was deemed unaccpetable
        if check_toxicity(input_essay) == True:
            return redirect(url_for('prompt'))
        



        #TODO check if is used, for now doesnt seem like using for analysis?
        #will display back their essay on page
        response_list[0] = input_essay

        try:
            current_prompt = prompts_collection.find_one(
                {"active": True, "type": mode},  
                {"type": 1, "prompt": 1, "_id": 0}  
            )
        except Exception as e:
            logger.error(f"Database issue while finding current prompt on analysis page: {e}")
            return render_template('landing_page.html', error=str(e))
        

        #####QUERY 1#####
        #get current prompt
  
        #system message for gpt
        system_message = f"""The user has written this writing as creative writing excersise. Write a 3 to 4 sentence paragraph giving your feedback to the writer. Be honest, if the writing is very poor say so, but if it very good say that too. If it is unintelligble do not be afraid to say so. Following the prompt I will show is very important to your analysis, if it does not follow the prompt mention that and make it a big part of your analysis.
        The writing was based on the following prompt, so keept that in mind for all of your feedback you will give:
        {current_prompt['prompt']}
        Also, if the user has typed an unintelligible input or something that does not make sense such as: all whitespace characters, random characters, gibberish, etc... Then just respond with only one & character, nothing else except the & character if the input is invalid."""

        messages_array = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": input_essay}
        ]

        #Text analysis in paragraph form query
        response = client.chat.completions.create(
            model="gpt-4",
            max_tokens=200,
            messages=messages_array
        )

        #response given by gpt
        text_analysis = response.choices[0].message.content

        #if there is an invalid input e.g whitespaces only or gibberish, the response back from gpt is &. 
        #eventually needs to lead to error page
        stripped_text= text_analysis.strip() #strip takes all leading and trailing whitespaces
        if stripped_text == '&':
            return redirect('/difficulty')
        
        #add to messages_array for context on further analysis
        messages_array.append({"role": "assistant", "content": text_analysis}) 

        #add to list to be displayed in html
        response_list[1] = text_analysis

       
        #####QUERY 2#####
        #isolated parts of text analysis query
        system_message2 ="""
        Please isolate two specific sentences from the writing that you found particularly interesting, 
        and provide a 1 or 2 sentence analysis for each. It's crucial that you format your response precisely as follows:
        'First quote ||| First analysis ||| Second quote ||| Second analysis'. 

        Use '|||' to separate:
        1. The first quote from the first analysis.
        2. The first analysis from the second quote.
        3. The second quote from the second analysis.

        Each analysis should consist of only one sentence. Please do not number your responses or include additional text or punctuation outside the specified format.
        """


        messages_array.append({"role": "system", "content": system_message2})

        response = client.chat.completions.create(
            model="gpt-4", #needs to be gpt4, gpt3.5 cannot follow instructions
            max_tokens=200,
            messages=messages_array
        )
        isolated_analysis = response.choices[0].message.content
        messages_array.append({"role": "assistant", "content": isolated_analysis})

        #split on the special character told to gpt
        parts = isolated_analysis.split('|||')

        text_parts = [part.strip() for part in parts[::2]]  #extract the text every 2nd element from beginning
        analysis_parts = [part.strip() for part in parts[1::2]]  #extract the analysis every 2nd element from 1st element
   

        #####QUERY 3#####
        #isolated parts of grammar breakdown query
        system_message3 ="""
        Please isolate two specific sentences from the writing that you found have grammar mistakes or exceptional grammar, 
        and provide a 1 or 2 sentence analysis for each. It's crucial that you format your response precisely as follows:
        'First quote ||| First breakdown||| Second quote ||| Second breakdown'. 

        Use '|||' to separate:
        1. The first quote from the first breakdown.
        2. The first breakdown from the second quote.
        3. The second quote from the second breakdown.

        Each breakdown should consist of only one sentence. Please do not number your responses or include additional text or punctuation outside the specified format. Each of the breakdown should be unique, do not say the same thing. Try not to use the First or Second analysis sentences unless necessary due to length of text given to you.
        """


        messages_array.append({"role": "system", "content": system_message3})

        response = client.chat.completions.create(
            model="gpt-4", #needs to be gpt4, gpt3.5 cannot follow instructions
            max_tokens=200,
            messages=messages_array
        )
        grammar_analysis = response.choices[0].message.content
        messages_array.append({"role": "assistant", "content": grammar_analysis})

        #split on the special character told to gpt
        parts = grammar_analysis.split('|||')
        
        #for grammar breakdown
        text_parts2 = [part.strip() for part in parts[::2]]  #extract the text every 2nd element from beginning
        analysis_parts2 = [part.strip() for part in parts[1::2]]  #extract the analysis every 2nd element from 1st element

        #####QUERY 4#####
        #get numerical score
        system_message4 = "Now write a numerical score from 0-1000 for the original writing. Here is the rubric: 600 points for how well you think it was written and followed the prompt(if it didn't follow the prompt at all and seems irrelevant don't give it any of the 600 points), 200 points for length, and 200 points for your choosing for these last 200 points make it very difficult to get all 200 but it is possible but has to be a perfect piece of writing in your mind. The response is only the number, nothing else."
        messages_array.append({"role": "system", "content": system_message4})

        response = client.chat.completions.create(
            model="gpt-4",
            max_tokens=200,
            messages=messages_array
        )
        score_analysis = response.choices[0].message.content

        #an edge case when response is not a string containing digits
        if not score_analysis.isdigit():
            return redirect('/difficulty')
        
        response_list[2] = score_analysis 

        ####Store in database ####
        #store essay and score in essays_collection in db
        essay_document = {
            'user_id': ObjectId(current_user.id),
            'text': input_essay,
            'mode': mode,
            'score': int(score_analysis)
            #add date if we wanted history up to a certain point later
        }

        try:
            essays_collection.insert_one(essay_document)
        except Exception as e:
            logger.error(f"Database issue while inserting essay: {e}")
            return render_template('landing_page.html', error=str(e))

        return render_template('analysis.html', response_list=response_list, text_parts = text_parts, analysis_parts = analysis_parts,text_parts2=text_parts2,analysis_parts2=analysis_parts2)
    else:
        #TODO - make sure works 100% eventually
        return render_template('analysis.html', response_list=response_list, text_parts = text_parts, analysis_parts = analysis_parts,text_parts2=text_parts2,analysis_parts2=analysis_parts2)


#usermixin has methods that check if the user is authenticated and other important things
class User(UserMixin):
    def __init__(self, username, id):
        self.username = username
        self.id = str(id)  

#find the user from the database
@login_manager.user_loader #tells flask to use this function for user retrieval
def load_user(user_id):
    user = users_collection.find_one({"_id": ObjectId(user_id)})  #need to use ObjectID or breaks
    if user:
        return User(username=user['username'], id=user['_id'])
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    #get username and password from form
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            #find user in database
            user = users_collection.find_one({'username': username})
            #check the username and password
            if user and check_password_hash(user['password'], password):
                #login and go to landing page
                user_obj = User(username=user['username'], id=user['_id'])
                login_user(user_obj)
                return redirect(url_for('landing_page'))
            else:
                #display error message
                flash('Invalid credentials. Please try again.')
        except Exception as e:
            logger.error(f"Error occured in login page: {e}")
            return render_template('landing_page.html', error=str(e))
    return render_template('login.html')

#logout and redirect to login
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/create', methods=['GET', 'POST'])
def create_account():
    #get info from create account form
    if request.method == 'POST':
        try:
            #creating account from username, password, and email
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            
            #check database for existing user/email, they have to be unique
            existing_user = users_collection.find_one({'username': username})
            existing_email = users_collection.find_one({'email': email})
            
            if existing_user or existing_email:
                if existing_user:
                    flash('Username already exists.')
                if existing_email:
                    flash('Email already registered.')
                return redirect(url_for('create_account'))
            
            #hash the password then insert into database
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            users_collection.insert_one({'username': username, 'email': email, 'password': hashed_password})
            flash('Account created successfully!')
            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Error occured in create account page: {e}")
            return render_template('landing_page.html', error=str(e))
    return render_template('create_account.html')


@app.route('/about')
def about():
    return render_template('about.html')

#this is running at the start of app.py
def init_prompts():
    #if current state_collection is empty generate new prompt(this should be on start)
    if state_collection.count_documents({}) < 1:
        initial_prompts = helper_generate_prompts()
        state_collection.insert_one({
            "current_prompts": initial_prompts,
            "last_gen_time": datetime.datetime.now()
        })
        #create indexes for RAG system - specific documentation on function above
        create_similarity_index('prompts')
    return

if __name__ == '__main__':
    init_prompts()
    app.run(debug=True)
