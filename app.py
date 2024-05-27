from flask import Flask, request, render_template
from openai import AzureOpenAI
import os
from dotenv import load_dotenv
from pymongo import MongoClient

app = Flask(__name__)

load_dotenv()

#variables for api
api_key = os.getenv("AZURE_OAI_KEY")
azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
api_version = os.getenv("AZURE_OAI_VERSION")


#route for the landing page
@app.route('/')
def landing_page():
    return render_template('landing_page.html')

#route for the chat page
@app.route('/chat', methods=['POST', 'GET'])
def ask_openai():
    response = ""
    if request.method == 'POST':
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )

        #system message for gpt
        system_message = "You are a yugioh master. Answer in long sentences"

        #get message from form submission on button press
        user_input = request.form['message']

        messages_array = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_input}
        ]

        response = client.chat.completions.create(
            model="gpt-35-turbo",
            max_tokens=200,
            messages=messages_array
        )

        #response given by gpt
        generated_text = response.choices[0].message.content
        return render_template('chat.html', response_text=generated_text)
        #load page regardless
    else:
        return render_template('chat.html', response=response)
    

@app.route('/prompt')
def prompt():
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
    return render_template('prompt.html', response_text=generated_text)

@app.route('/analysis')
def analysis():
    return render_template('analysis.html')

if __name__ == '__main__':
    app.run(debug=True)
