# knight-hacks 
# LawyerUP 
  ### This is our hackathon submission for the Morgan&Morgan Challenge.
  ### Team Members:
  #### 1. Mohammad Aatif Sheikh
  #### 2. Naman Sehgal
  #### 3. Kanishk Singh Chauhan
  #### 4. Paramveer Singh Bhele
# Chatbot Application with Flask and OpenAI GPT-3.5-turbo

This is a simple chatbot application that uses the Flask framework and OpenAI's GPT-3.5-turbo model to provide responses to user queries. The chatbot assists users in finding lawyers based on their case type.

## Features

- Generates responses using OpenAI's GPT-3.5-turbo model.
- Recommends lawyers based on user-provided case types.
- Provides information about recommended lawyers, including their contact details, areas of expertise, and experience.

## Prerequisites

Before running the application, ensure you have the following prerequisites installed:

- Python 3.x: You can download Python from [python.org](https://www.python.org/downloads/).
- Flask: Install Flask using `pip`:
  ```bash
  pip install flask
  
OpenAI Python Client: Install the OpenAI Python client library using `pip`:
  ```bash
  pip install openai
```

## Getting Started
Clone this repository to your local machine:
```bash
git clone https://github.com/your-username/chatbot-app.git
```
Navigate to the project directory:
```bash
cd chatbot-app
```

## Set up your OpenAI API key:

Create an account on the OpenAI platform.
Generate an API key from the OpenAI platform.
Replace 'Your_API_key' in app.py with your API key.
Prepare the lawyer and case data:

Create two JSON files: lawyer_database.json and case_database.json.
Populate these files with your lawyer and case data in the respective formats.
Run the Flask application:
```bash
python app.py
```
The Flask application will start and listen on http://localhost:5000.

## Usage
Open your web browser and navigate to http://localhost:5000 to access the chat interface.

Enter a case type or query in the chat input field and press Enter or click the Send button.

The chatbot will provide responses, including recommended lawyers based on the case type.

## CORS Configuration
The application uses CORS to allow requests from the frontend. In app.py, the CORS configuration is set to allow requests from http://127.0.0.1:8000. You can adjust this as needed to match your frontend's URL.

## Customization
You can customize the chatbot's responses and conversation flow by modifying the chatbot_response function in app.py.
Adjust the MAX_REQUESTS_PER_MINUTE variable in script.js to match your subscription level with OpenAI.

## Acknowledgments
This project was created using Flask and OpenAI's GPT-3.5-turbo model.
Special thanks to the Flask and OpenAI communities for their contributions and support.

Please make sure to replace the placeholder values and URLs with your actual data and URLs. Additionally, you can add more sections or details as needed for your project's documentation.


