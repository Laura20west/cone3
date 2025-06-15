from flask import Flask, request, jsonify
from datetime import datetime
import os
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Configuration
LOG_DIR = 'chat_logs'
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

        return jsonify({"status": "success", "message": f"Processed {len(messages)} messages"}), 200

    except Exception as e:
        app.logger.error(f"Error processing request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
