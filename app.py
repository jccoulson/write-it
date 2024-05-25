from flask import Flask, request, jsonify, render_template
from openai import AzureOpenAI
import os
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

#variables for api
api_key = os.getenv("AZURE_OAI_KEY")
azure_endpoint = os.getenv("AZURE_OAI_ENDPOINT")
api_version = os.getenv("AZURE_OAI_VERSION")

@app.route('/', methods=['POST', 'GET'])
def ask_openai():
    response = ""
    if request.method == 'POST':
        #try:
        client = AzureOpenAI(                
                azure_endpoint=azure_endpoint,                 
                api_key=api_key,                  
                api_version=api_version
        )
        #system prompt for chatbot
        system_message = "You are a yugioh master. Answer in long sentences"

        #get message from form submite on button press
        user_input = request.form['message']

        messages_array = [{"role": "system", "content": system_message},
                        {"role": "user", "content": user_input}]

        response = client.chat.completions.create(
            #can change other params like temp
            model="gpt-35-turbo",
            max_tokens=200,
            messages=messages_array
        )
        
        #response
        generated_text = response.choices[0].message.content
        return render_template('index.html', response_text=generated_text)


    else:
        return render_template('index.html', response=response)

if __name__ == '__main__':
    app.run(debug=True)
