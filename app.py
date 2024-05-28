from flask import Flask, request, render_template
from openai import AzureOpenAI
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import datetime
import time

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

current_prompts = generate_prompts()
last_gen_time = datetime.date.today()

@app.route('/prompt')
def prompt():
    global last_gen_time
    global current_prompts
    print(last_gen_time)

    #check if its been a day since someone has alst been on page to generate new prompt
    if last_gen_time < datetime.date.today():
        current_prompts = generate_prompts()
        last_gen_time = datetime.date.today()
    return render_template('prompt.html', response_text=current_prompts)

@app.route('/analysis', methods=['POST'])
def analysis():
     
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
            model="gpt-4",
            max_tokens=200,
            messages=messages_array
        )
        isolated_analysis = response.choices[0].message.content
        messages_array.append({"role": "assistant", "content": isolated_analysis})

        print(isolated_analysis)
        parts = isolated_analysis.split('|||')

        text_parts = [part.strip() for part in parts[::2]]  #extract the text
        analysis_parts = [part.strip() for part in parts[1::2]]  #extract the analysis
   
        time.sleep(5.5)

        #####QUERY 3#####
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
    

if __name__ == '__main__':
    app.run(debug=True)
