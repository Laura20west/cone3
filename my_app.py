from flask import Flask, request, jsonify
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
import os

app = Flask(__name__)

# Configuration
LOG_DIR = 'chat_logs'
LOG_FILE = os.path.join(LOG_DIR, 'chat_messages.log')
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5
MAX_MEMORY_MESSAGES = 1000  # Keep last 1000 messages in memory

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Set up file logging
file_handler = RotatingFileHandler(
    LOG_FILE, 
    maxBytes=MAX_LOG_SIZE, 
    backupCount=BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# In-memory message storage
message_store = deque(maxlen=MAX_MEMORY_MESSAGES)

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def receive_chat_messages():
    """Endpoint to receive chat messages from Tampermonkey"""
    if request.method == 'OPTIONS':
        response = jsonify({"status": "success"})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response

    try:
        data = request.get_json()
        if not data or 'messages' not in data:
            app.logger.error("Invalid request: no messages in payload")
            return jsonify({"status": "error", "message": "Invalid request format"}), 400

        messages = data['messages']
        if not isinstance(messages, list):
            return jsonify({"status": "error", "message": "Messages should be an array"}), 400

        new_messages = []
        for msg in messages:
            # Validate required fields
            if not all(key in msg for key in ['id', 'text', 'is_user', 'timestamp']):
                app.logger.warning(f"Incomplete message received: {msg}")
                continue

            # Check if message already exists
            if any(m['id'] == msg['id'] for m in message_store):
                continue

            # Create message object
            message_obj = {
                'id': msg['id'],
                'text': msg['text'],
                'is_user': msg['is_user'],
                'sender': 'user' if msg['is_user'] else 'agent',
                'timestamp': msg['timestamp'],
                'received_at': datetime.utcnow().isoformat() + 'Z',
                'platform': 'myoperatorservice'
            }
            
            # Store in memory and log to file
            message_store.append(message_obj)
            app.logger.info(f"Message received: {message_obj}")
            new_messages.append(message_obj)

        response = jsonify({
            "status": "success",
            "message": f"Processed {len(messages)} messages",
            "stored": len(new_messages)
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        app.logger.error(f"Error processing messages: {str(e)}")
        response = jsonify({"status": "error", "message": str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Endpoint to retrieve stored messages"""
    try:
        # Get query parameters with defaults
        limit = min(int(request.args.get('limit', 100)), 1000)
        is_user = request.args.get('is_user')
        
        # Filter messages if is_user parameter provided
        messages = list(message_store)
        if is_user is not None:
            filter_user = is_user.lower() == 'true'
            messages = [m for m in messages if m['is_user'] == filter_user]
        
        # Return most recent messages first
        messages.reverse()
        response = jsonify(messages[:limit])
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    
    except Exception as e:
        app.logger.error(f"Error retrieving messages: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/messages', methods=['GET'])
def message_viewer():
    """Web interface to view messages"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Chat Message Viewer</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .message { margin-bottom: 15px; padding: 10px; border-radius: 5px; }
            .user { background-color: #e3f2fd; }
            .agent { background-color: #f5f5f5; }
            .timestamp { color: #666; font-size: 0.8em; }
            .controls { margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>Chat Messages</h1>
        <div class="controls">
            <label>
                <input type="checkbox" id="filter-user" onchange="loadMessages()">
                Show only user messages
            </label>
            <button onclick="loadMessages()">Refresh</button>
        </div>
        <div id="messages-container"></div>
        
        <script>
            function formatDate(isoString) {
                const date = new Date(isoString);
                return date.toLocaleString();
            }
            
            async function loadMessages() {
                const filterUser = document.getElementById('filter-user').checked;
                const url = `/api/messages?limit=100${filterUser ? '&is_user=true' : ''}`;
                
                try {
                    const response = await fetch(url);
                    const messages = await response.json();
                    
                    const container = document.getElementById('messages-container');
                    container.innerHTML = '';
                    
                    if (messages.length === 0) {
                        container.innerHTML = '<p>No messages found</p>';
                        return;
                    }
                    
                    messages.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = `message ${msg.is_user ? 'user' : 'agent'}`;
                        div.innerHTML = `
                            <div class="timestamp">${formatDate(msg.timestamp)} (received: ${formatDate(msg.received_at)})</div>
                            <strong>${msg.sender}:</strong>
                            <div>${msg.text}</div>
                        `;
                        container.appendChild(div);
                    });
                } catch (error) {
                    console.error('Error loading messages:', error);
                    document.getElementById('messages-container').innerHTML = 
                        '<p>Error loading messages. Check console for details.</p>';
                }
            }
            
            // Load messages when page loads
            document.addEventListener('DOMContentLoaded', loadMessages);
        </script>
    </body>
    </html>
    """

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "message_count": len(message_store),
        "timestamp": datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
