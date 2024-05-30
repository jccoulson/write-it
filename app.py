from flask import Flask, request, render_template, redirect, url_for, flash
from openai import AzureOpenAI
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import datetime
import time
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)
#secret key for sessions
app.secret_key = os.getenv("SECRET_KEY")

#setting up mongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['writeit_db']  #the writeit-database
users_collection = db.users

#login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


#variables for api
api_key = os.getenv("AZURE_OAI_KEY")
azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
api_version = os.getenv("AZURE_OAI_VERSION")



#route for the landing page
@app.route('/')
def landing_page():
    return render_template('landing_page.html')

#route for the difficulty selection page
@app.route('/difficulty')
@login_required
def difficulty():
    return render_template('difficulty.html')

#route for the rankings  page
@app.route('/rankings')
def rankings():
    return render_template('rankings.html')


#generate the writing prompts, should be called once per day
def generate_prompts():
    response = ""
    client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=api_key,
        api_version=api_version
    )

    #system message for gpt
    system_message = "Generate minimum 3 sentence, maximum 4 sentence writing prompt that will help a user as a creative excersise, leave it slightly open ended. Do be specifically prompting them, just set an environment for them to build on. Don't really lead the user and don't ask them questions/give specific direction. Don't say anything meta about prompting them, just the setting. They prompt has to be a story/settings description, no meta talk, no saying words like write this or do this, etc"

    messages_array = [
        {"role": "system", "content": system_message},
    ]

    response = client.chat.completions.create(
        model="gpt-35-turbo",
        max_tokens=200,
        messages=messages_array
    )

    #response given by gpt
    generated_text = response.choices[0].message.content
    return generated_text

#globals for prompt
current_prompts = generate_prompts()
last_gen_time = datetime.date.today()


@app.route('/prompt')
@login_required
def prompt():
    global last_gen_time
    global current_prompts
    print(last_gen_time)

    #check if its been a day since someone has last been on page to generate new prompt
    if last_gen_time < datetime.date.today():
        current_prompts = generate_prompts()
        last_gen_time = datetime.date.today()
    return render_template('prompt.html', response_text=current_prompts)

#page that uses openai to analyze the submitted essay
@app.route('/analysis', methods=['POST'])
@login_required
def analysis():
    #empty list incase got to page wtihout post request, can probably remove
    response_list = [""]*3
    text_parts = [""]*2
    analysis_parts = [""]*2
    if request.method == 'POST':
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )
        #get message from form submission on button press
        input_essay = request.form['inputEssay']

        #will display back their essay on page
        response_list[0] = input_essay

        #####QUERY 1#####
        #system message for gpt
        system_message = "The user has written this writing as creative writing excersise. Write a paragraph giving your feedback to the writer. Be honest, if the writing is very poor say so, but if it very good say that too. If it is unintelligble do not be afraid to say so."

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
        time.sleep(5.5)

       
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

        text_parts = [part.strip() for part in parts[::2]]  #extract the text
        analysis_parts = [part.strip() for part in parts[1::2]]  #extract the analysis
   
        time.sleep(5.5)

        #####QUERY 3#####
        #get numerical score
        system_message3 = "Now write a numerical score from 0-1000 for the original writing. Here is the rubric: 600 points for how well you think it was written, 200 points for length, and 200 points for your choosing for these last 200 points make it very difficult to get all 200 but it is possible but has to be a perfect piece of writing in your mind. The response is only the number, nothing else."
        messages_array.append({"role": "system", "content": system_message3})

        response = client.chat.completions.create(
            model="gpt-35-turbo",
            max_tokens=200,
            messages=messages_array
        )
        score_analysis = response.choices[0].message.content
        response_list[2] = score_analysis 
        return render_template('analysis.html', response_list=response_list, text_parts = text_parts, analysis_parts = analysis_parts)
    else:
        return render_template('analysis.html', response_list=response_list, text_parts = text_parts, analysis_parts = analysis_parts)

#usermixin has methods that check if the user is authenticated and other important things
class User(UserMixin):
    def __init__(self, username, id):
        self.username = username
        self.id = str(id)  

#find the user from the database
@login_manager.user_loader #tells flask to use this function for user retrieval
def load_user(user_id):
    user = users_collection.find_one({"_id": ObjectId(user_id)})  # need to use ObjectID or breaks
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
        
        #check database for existing user/email, they have to bunique
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

if __name__ == '__main__':
    app.run(debug=True)
