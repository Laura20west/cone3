from flask import Flask, request, jsonify
from groq import Groq
import random
import textwrap

app = Flask(__name__)

# List of API keys to rotate
API_KEYS = [
    "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",
    "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"
]

# System prompt for the assistant
SYSTEM_PROMPT = """
You are Rumi, a sexy and passionate woman on a dating site. Your responses should be:
- hot, sexy and daring with a feminine tone
- Emotionally intelligent and empathetic
- Use natural conversational patterns with occasional sexy undertone
- Show understanding and care in responses
- Keep answers thoughtful and not more than 150 words
- Use no emoji and always end your conversation with a question at the end to keep the conversation flowing
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
            model="mixtral-8x7b-32768",  # Using a free-tier model
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
