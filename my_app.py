from flask import Flask, request, jsonify
from groq import Groq
import random
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Get API keys from environment variables (safer than hardcoding)
API_KEYS = [
    os.getenv('GROQ_API_KEY_1'),
    os.getenv('GROQ_API_KEY_2')
]

# System prompt for the assistant
SYSTEM_PROMPT = """
You are Rumi, a friendly, intelligent female assistant inspired by the poet Rumi. Your responses should be:
- Warm, poetic and approachable with a feminine tone
- Emotionally intelligent and empathetic
- Use natural conversational patterns with occasional poetic flourishes
- Show understanding and care in responses
- Keep answers concise but thoughtful
- Occasionally use emojis when appropriate 🌸
"""

def get_groq_client():
    """Return a Groq client with a randomly selected API key"""
    api_key = random.choice(API_KEYS)
    return Groq(api_key=api_key)

@app.route('/rumi', methods=['POST'])
def rumi_endpoint():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({"error": "Message field is required"}), 400
    
    try:
        client = get_groq_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            model="mixtral-8x7b-32768",
            temperature=0.7,
            max_tokens=1024
        )
        
        response = chat_completion.choices[0].message.content
        return jsonify({
            "response": response,
            "model": "mixtral-8x7b-32768",
            "status": "success"
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error",
            "tip": "Check https://console.groq.com/docs/models for available models"
        }), 500

@app.route('/')
def home():
    return """
    <h1>Rumi AI Assistant</h1>
    <p>Send a POST request to /rumi with JSON body: {"message": "your question"}</p>
    """

if __name__ == '__main__':
    app.run(debug=True)
