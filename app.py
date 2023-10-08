from flask import Flask, request, jsonify
import openai
import json
from flask_cors import CORS
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Define your chatbot logic here
CORS(app, resources={r"/chat": {"origins": "http://127.0.0.1:8000"}})

# Initialize OpenAI API client with your API key
api_key = os.getenv("OPENAI_API_KEY")

# Load lawyer and case data from JSON files
with open('lawyer_database.json', 'r') as lawyer_file:
    lawyer_data = json.load(lawyer_file)

with open('case_database.json', 'r') as case_file:
    case_data = json.load(case_file)

def chatbot_response(user_message):
    chatbot_reply = ""
    # Define user and assistant messages for conversation
    conversation = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user_message},
    ]

    # Generate a response from OpenAI's GPT-3.5-turbo model
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=conversation,
    )

    # Extract OpenAI's response
    openai_reply = response['choices'][0]['message']['content']

    # Check if the user's message matches any case type
    user_message = user_message.lower()
    matching_cases = []

    for case in case_data:
        if user_message in case["Case Type"].lower():
            matching_cases.append(case)

    if matching_cases:
        # If there are matching cases, recommend lawyers based on the first matching case
        recommended_lawyer_ids = matching_cases[0]["Recommended Lawyer ID"]

        # Find the corresponding lawyers in the lawyer database
        recommended_lawyers = []
        for lawyer in lawyer_data:
            if lawyer["Lawyer ID"] in recommended_lawyer_ids:
                recommended_lawyers.append(lawyer)

        # Generate a response with lawyer recommendations
        if recommended_lawyers:
            chatbot_reply += "Based on your case type, here are some recommended lawyers:\n"
            for lawyer in recommended_lawyers:
                chatbot_reply += "Lawyer: {}\n".format(lawyer["Lawyer's Name"])
                chatbot_reply += f"Contact Information: {lawyer['Contact Information']['Email']} | {lawyer['Contact Information']['Phone']}\n"
                chatbot_reply += f"Areas of Expertise: {', '.join(lawyer['Areas of Expertise'])}\n"
                chatbot_reply += f"Experience: {lawyer['Experience']} years\n\n"
        else:
            chatbot_reply += "I couldn't find any recommended lawyers for your case type."
    else:
        # If no matching case type, provide a default response
        chatbot_reply += "I'm here to help. Please specify your case type for lawyer recommendations."

    return chatbot_reply

@app.route('/chat', methods=['OPTIONS'])
def handle_options():
    return '', 200, {
        'Access-Control-Allow-Origin': 'http://127.0.0.1:8000',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST',
    }

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()  # Parse JSON data from the request's body
    user_message = data['message']
    chatbot_reply = chatbot_response(user_message)
    return jsonify({'reply': chatbot_reply})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
