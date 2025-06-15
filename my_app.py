from flask import Flask, request, jsonify
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure PostgreSQL connection
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Message Model
class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(100), nullable=False, unique=True)
    text = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    sender = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    received_at = db.Column(db.DateTime, nullable=False)
    platform = db.Column(db.String(50), default='myoperatorservice')

    def __repr__(self):
        return f'<Message {self.message_id}>'

# Create tables (only needed once)
with app.app_context():
    db.create_all()

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
            if ChatMessage.query.filter_by(message_id=msg['id']).first():
                continue

            # Create new message
            new_msg = ChatMessage(
                message_id=msg['id'],
                text=msg['text'],
                is_user=msg['is_user'],
                sender='user' if msg['is_user'] else 'agent',
                timestamp=datetime.fromisoformat(msg['timestamp'].rstrip('Z')),
                received_at=datetime.utcnow()
            )
            db.session.add(new_msg)
            new_messages.append(new_msg)

        db.session.commit()
        app.logger.info(f"Stored {len(new_messages)} new messages")

        response = jsonify({
            "status": "success",
            "message": f"Processed {len(messages)} messages",
            "stored": len(new_messages)
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error processing messages: {str(e)}")
        response = jsonify({"status": "error", "message": str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Endpoint to retrieve stored messages"""
    try:
        # Get query parameters
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))
        is_user = request.args.get('is_user')
        
        # Build query
        query = ChatMessage.query.order_by(ChatMessage.timestamp.desc())
        
        if is_user is not None:
            query = query.filter_by(is_user=is_user.lower() == 'true')
        
        messages = query.limit(limit).offset(offset).all()
        
        response = jsonify([{
            "id": msg.message_id,
            "text": msg.text,
            "is_user": msg.is_user,
            "sender": msg.sender,
            "timestamp": msg.timestamp.isoformat(),
            "received_at": msg.received_at.isoformat(),
            "platform": msg.platform
        } for msg in messages])
        
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    
    except Exception as e:
        app.logger.error(f"Error retrieving messages: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
