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
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import numpy as np
from detoxify import Detoxify



load_dotenv()

app = Flask(__name__)
#secret key for sessions
app.secret_key = os.getenv("SECRET_KEY")

#setting up mongoDB connection
client = MongoClient(os.getenv("AZURE_MONGO_CONNECTION_STRING"))
db = client['writeit_db']  #the writeit-database
users_collection = db.users
#collection for daily essays
essays_collection = db.essays
#collection for daily prompts
prompts_collection = db.prompts

#login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

#variables for api
api_key = os.getenv("AZURE_OAI_KEY")
azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
api_version = os.getenv("AZURE_OAI_VERSION")

client = AzureOpenAI(
    azure_endpoint=azure_endpoint,
    api_key=api_key,
    api_version=api_version
)

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
    if request.method == 'POST':
        mode = request.form['mode']
        user_id = request.form['user_id']
        username = request.form['username']
        essay_id = request.form['essay_id']
        #grab the text from essay collection based on user_id and mode
        essay=essays_collection.find_one({'user_id':ObjectId(user_id),'mode':mode, '_id':ObjectId(essay_id)}, {'text':1})
        essay = escape(essay['text']) #remove any html tags user added just in case of malicious actors

        #send the text and username
        return render_template('read.html', essay=essay, username=username, mode=mode)
    else:
        return redirect('/rankings')


@app.route('/temp')
def temp():
    return render_template('temp.html')

#currently is rankings from all time, take out the essay_id_list when we want to do current rankings and uncomment the essay clear on prompt generation
#route for the rankings  page
@app.route('/rankings')
def rankings():
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

#pre trained sentence transformer model for generating embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')

#check similarity with existing prompts
def is_prompt_similar(new_prompt, threshold=0.8):
    #get all prompts in database
    results = list(prompts_collection.find({}, {"prompt": 1, "_id": 0}))
    
    #if empty then return false, e.g. no need to make comparisons
    if not results:
        print("No prompts found in the database.")
        return False
    
    new_prompt_embedding = model.encode([new_prompt])
    
    #get all existing prompts and from the database and embedd them
    all_prompts = list(prompts_collection.find({}, {"prompt": 1, "_id": 0}))
    all_prompts_text = [item["prompt"] for item in all_prompts]
    all_embeddings = model.encode(all_prompts_text)
    
    #use cosine similarity between new prompt and all existing prompts
    similarities = cosine_similarity(new_prompt_embedding, all_embeddings)
    
    #if similarity exceeds threshhold(0.8) then return true(it is similar)
    max_similarity = np.max(similarities)
    print("In is_prompt_similar - max similarity:", max_similarity)
    print("In is_prompt_similar - similarities:", similarities)

    return max_similarity >= threshold

#generate the writing prompts, should be called once per day
def helper_generate_prompts():
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

    #if prompt unique, then store and move on to next prompt type, if not unique, keep re-generating with calling for is_prompt_unique func
    for prompt_type, system_message in prompt_types.items():
        new_prompt = generate_prompt(system_message)
        if(is_prompt_similar(new_prompt)):
            new_prompt = generate_prompt(system_message)
            list_of_prompts.append({"type": prompt_type, "prompt": new_prompt})
        list_of_prompts.append({"type": prompt_type, "prompt": new_prompt})
    

    prompts_collection.update_many({}, {"$set": {"active": False}})  #set all old prompts to not active
    for prompt in list_of_prompts:
        prompts_collection.insert_one({
            "type": prompt["type"],
            "prompt": prompt["prompt"],
            "date": datetime.datetime.now(),
            "active": True
        })

    return list_of_prompts

####################### COMMENT OUT current_prompts WHEN DEVELOPING TO PRESERVE TOKENS ########################
#globals for prompt
#current_prompt is a list of dictionaries with key:["type"] key:["prompt"]
current_prompts = helper_generate_prompts()
last_gen_time = datetime.date.today()


@app.route('/prompt', methods=['POST','GET'])
@login_required
def prompt():
    global last_gen_time
    global current_prompts

    #check if its been a day since someone has last been on page to generate new prompt
    if last_gen_time < datetime.date.today():
        current_prompts = helper_generate_prompts()
        last_gen_time = datetime.date.today()
    
    ### post check for development ###
    if request.method == 'POST':
        mode = request.form['mode']
        if mode == 'normal':
            return render_template('prompt.html',response_text=current_prompts[0]["prompt"], current_mode = mode) #pass difficulty to prompt page for later storage
        elif mode == 'creative':
            return render_template('prompt.html',response_text=current_prompts[1]["prompt"], current_mode = mode)
        elif mode == 'challenge':
            return render_template('prompt.html',response_text=current_prompts[2]["prompt"], current_mode = mode)
    else:
        return redirect('/difficulty')
   

def check_toxicity(text):
    results = Detoxify('original').predict(text)

    #adjust threshold of toxicity if needed
    #there are multiple types such as toxicity, obscene, threat, etc
    needs_review = any(value >= 0.7 for value in results.values())
    if needs_review:
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

        if toxicity_analysis == "0":
            return False
        else:
            return True

    return False
        
    

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
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )
        #get form data from submission of essay
        input_essay = request.form['inputEssay']
        mode = request.form['mode']

        #TODO eventually redirect to page to tell them their content was deemed unaccpetable
        if check_toxicity(input_essay) == True:
            return redirect(url_for('prompt'))
        



        #TODO check if is used, for now doesnt seem like using for analysis?
        #will display back their essay on page
        response_list[0] = input_essay


        current_prompt = prompts_collection.find_one(
            {"active": True, "type": mode},  
            {"type": 1, "prompt": 1, "_id": 0}  
        )
        

        #####QUERY 1#####
        #get current prompt
  
        #system message for gpt
        system_message = f"""The user has written this writing as creative writing excersise. Write a 3 to 4 sentence paragraph giving your feedback to the writer. Be honest, if the writing is very poor say so, but if it very good say that too. If it is unintelligble do not be afraid to say so. Following the prompt I will show is very important to your analysis, if it does not follow the prompt mention that and make it a big part of your analysis.
        The writing was based on the following prompt, so keept that in mind for all of your feedback you will give:
        {current_prompt['prompt']}
        """

        messages_array = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": input_essay}
        ]

        #Text analysis in paragraph form query
        response = client.chat.completions.create(
            model="gpt-35-turbo",
            max_tokens=200,
            messages=messages_array
        )

        #response given by gpt
        text_analysis = response.choices[0].message.content

        #add to messages_array for context on further analysis
        messages_array.append({"role": "assistant", "content": text_analysis}) 

        #add to list to be displayed in html
        response_list[1] = text_analysis

       
        #####QUERY 2#####
        #isolated parts of text analysis query
        system_message2 ="""
        Please isolate two specific excerpts from the writing that you found particularly interesting, 
        and provide a brief analysis for each. It's crucial that you format your response precisely as follows:
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
        Please isolate two specific excerpts from the writing that you found have grammar mistakes or exceptional grammar, 
        and provide a brief breakdown for each. It's crucial that you format your response precisely as follows:
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
        response_list[2] = score_analysis 

        ####Store in database ####
        #store essay and score in essays_collection in db
        essay_document = {
            'user_id': ObjectId(current_user.id),
            'text': input_essay,
            'mode': mode,
            'score': score_analysis
            #add date if we wanted history up to a certain point later
        }
        essays_collection.insert_one(essay_document)

        return render_template('analysis.html', response_list=response_list, text_parts = text_parts, analysis_parts = analysis_parts,text_parts2=text_parts2,analysis_parts2=analysis_parts2)
    else:
        #TODO - fix this, doesn't work 
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
    return render_template('create_account.html')


@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)
