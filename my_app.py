from flask import Flask, request, jsonify
from datetime import datetime
import os
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Configuration
LOG_DIR = os.path.join(os.getcwd(), 'chat_logs')
LOG_FILE = os.path.join(LOG_DIR, 'chat_messages.log')
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Set up logging
handler = RotatingFileHandler(
    LOG_FILE, 
    maxBytes=MAX_LOG_SIZE, 
    backupCount=BACKUP_COUNT,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

@app.route('/api/chat', methods=['POST'])
def receive_chat_messages():
    """
    Endpoint to receive chat messages from the TamperMonkey script.
    """
    try:
        # Add CORS headers for web requests
        if request.method == 'OPTIONS':
            response = jsonify({"status": "success"})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', '*')
            response.headers.add('Access-Control-Allow-Methods', '*')
            return response

        data = request.get_json()
        if not data or 'messages' not in data:
            app.logger.error("Invalid request: no messages in payload")
            return jsonify({"status": "error", "message": "Invalid request format"}), 400

        messages = data['messages']
        if not isinstance(messages, list):
            app.logger.error("Invalid request: messages is not a list")
            return jsonify({"status": "error", "message": "Messages should be an array"}), 400

        # Process each message
        for msg in messages:
            if not all(key in msg for key in ['id', 'text', 'is_user', 'timestamp']):
                app.logger.warning(f"Incomplete message received: {msg}")
                continue

            # Log the message
            log_entry = {
                'id': msg['id'],
                'timestamp': msg['timestamp'],
                'type': 'user' if msg['is_user'] else 'agent',
                'message': msg['text'],
                'received_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            app.logger.info(f"Message received: {log_entry}")

        response = jsonify({"status": "success", "message": f"Processed {len(messages)} messages"})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200

    except Exception as e:
        app.logger.error(f"Error processing request: {str(e)}")
        response = jsonify({"status": "error", "message": str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
