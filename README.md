# Write-It
### By Jesse Coulson and Tamir Shem Tov
This project was developed during a Microsoft AI Hackathon and uses Azure services. The aim of our application is to assist writers in practicing and enhancing their creativity through AI-generated prompts. 
Each day, users are presented with three different prompts, categorized into unique 'modes.' Participants can respond to these prompts with essays, which are then evaluated and scored using OpenAI's models. Additionally, users have the opportunity to read essays submitted by others, compare scores, and view rankings on leaderboards for each mode. 
To maintain a high quality user experience, our application leverages Huggingface transformers for detecting inappropriate content and employs embeddings to check for prompt similarity on generation. MongoDB is used as our database to be able to track user progress.
## Page Breakdown
### Landing Page
- **Overview**: The landing page is the first thing users see when they visit our web application. It tells the user what the purpose of our application is and directs them to begin writing.
![landing_page](https://github.com/jccoulson/write-it/assets/28967794/06a81418-9257-4fac-8113-fc70e6c5c8e8)

### Difficulty Page
- **Overview**: The difficulty page allows participants to choose from three prompt types tailored to different writing preferences and challenges.
  - Each mode can only be attempted once per day.
  - **Normal Mode** offers a straightforward prompt with a 10-minute time limit.
  - **Challenge Mode** presents a syntactical challenge with 20 minutes to write, pushing the participant to have to go out of their comfort zone.
  - **Creative Mode** provides an unconventional prompt to inspire creative thinking, with 15 minutes to submit.
  
![difficulty](https://github.com/jccoulson/write-it/assets/28967794/cf746d6a-2e3a-4c64-ba3e-746eeb337b4c)

### Prompt Page
- **Overview**: This page displays the daily prompt generated for the selected difficulty.
Users can enter their responses in the text area and submit them for feedback. Prompts are generated once per day. To make sure no two prompts are close to identical we use the Hugging Face Sentence Transformer.
This transformer calculates embeddings for the current prompt and then we use cosine similarity to evaluate semantic similarity.
If the prompt is too similar to previous ones, passing a certain threshold of cosine similarity, a new prompt is generated to ensure users the variety.
Additionally, submissions are screened for toxicity using a model based on the BERT architecture from the Detoxify python library.
If a submission is found to be inappropriate, it is not analyzed further and the user is redirected.
![prompt](https://github.com/jccoulson/write-it/assets/28967794/6107f03c-dfdb-430e-b8d8-913db8dc0deb)

### Leaderboard Page
- **Overview**: The leaderboard page displays the top 10 users from each of the three writing modes. Participants can view and compare high-scoring essays by clicking on buttons next to the scores, allowing users to see how others have engaged with the prompt.
- ![leaderboard](https://github.com/jccoulson/write-it/assets/28967794/4f6767f2-8574-42a1-a38b-adcc41d7a9dd)


### Login/Create Account Page
- **Overview**: These pages allow users to register and login. Here participants can create an account to save their essays, track their progress, and view their rankings on the leaderboards. The design is straightforward to ensure ease of access and use, allowing users to quickly start using our application.
![login](https://github.com/jccoulson/write-it/assets/28967794/a7c9ad1c-dc49-44d9-83af-8abd3e4e8da0)
