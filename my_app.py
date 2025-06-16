from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Initialize Flask app
app = Flask(__name__)

# Configure SQLite database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_messages.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Message Model
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(100), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    profile_image = db.Column(db.String(255))
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'content': self.content,
            'timestamp': self.timestamp,
            'is_user': self.is_user,
            'profile_image': self.profile_image,
            'date_created': self.date_created.isoformat()
        }

# Create tables
with app.app_context():
    db.create_all()

@app.route('/receive_messages', methods=['POST'])
def receive_messages():
    try:
        data = request.json
        messages = data.get('messages', [])
        new_messages = 0

        for msg in messages:
            # Check if message already exists
            if not Message.query.filter_by(message_id=msg['id']).first():
                new_message = Message(
                    message_id=msg['id'],
                    content=msg['content'],
                    timestamp=msg['timestamp'],
                    is_user=msg['isUser'],
                    profile_image=msg['profileImage']
                )
                db.session.add(new_message)
                new_messages += 1

        db.session.commit()
        return jsonify({
            "status": "success",
            "received": len(messages),
            "new_messages": new_messages
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

@app.route('/get_messages', methods=['GET'])
def get_messages():
    try:
        # Get query parameters
        limit = request.args.get('limit', default=100, type=int)
        offset = request.args.get('offset', default=0, type=int)
        order = request.args.get('order', default='desc')  # 'asc' or 'desc'

        # Build query
        query = Message.query

        # Apply ordering
        if order.lower() == 'asc':
            query = query.order_by(Message.date_created.asc())
        else:
            query = query.order_by(Message.date_created.desc())

        # Apply pagination
        messages = query.offset(offset).limit(limit).all()

        return jsonify({
            "status": "success",
            "count": len(messages),
            "messages": [msg.to_dict() for msg in messages]
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

@app.route('/')
def index():
    return """
    <h1>Chat Message API</h1>
    <p>Endpoints:</p>
    <ul>
        <li>POST /receive_messages - Receive messages from Tampermonkey script</li>
        <li>GET /get_messages - Retrieve stored messages</li>
    </ul>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
