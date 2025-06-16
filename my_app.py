import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection function
def get_db_connection():
    conn = psycopg2.connect(
        host="dpg-d17cvhvdiees73e31160-a",
        database="monitor_pqit",
        user="monitor_pqit_user",
        password="JJQNlRr3IMOj2F6raAswYvj6Kcp7ok1Z",
        cursor_factory=RealDictCursor
    )
    return conn

# Initialize database tables
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create tables if they don't exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS data_entries (
            id SERIAL PRIMARY KEY,
            data JSONB NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            url TEXT
        );
        
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            entry_id INTEGER REFERENCES data_entries(id),
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            profile_username TEXT,
            timestamp TIMESTAMP WITH TIME ZONE,
            received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
        """)
        conn.commit()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

# Initialize database on startup
init_db()

@app.route('/api/data', methods=['POST'])
def receive_data():
    conn = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        # Validate required fields
        if 'messages' not in data or 'profile' not in data:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert main data entry
        cur.execute(
            "INSERT INTO data_entries (data, url) VALUES (%s, %s) RETURNING id",
            (json.dumps(data), data.get('url'))
        )
        entry_id = cur.fetchone()['id']
        
        # Insert messages
        for msg in data['messages']:
            cur.execute(
                """
                INSERT INTO messages 
                (entry_id, sender, content, profile_username, timestamp)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    entry_id,
                    msg.get('sender'),
                    msg.get('content'),
                    data['profile'].get('username'),
                    msg.get('timestamp')
                )
            )
        
        conn.commit()
        return jsonify({
            "status": "success", 
            "message": "Data stored successfully",
            "entry_id": entry_id
        }), 200
    
    except Exception as e:
        logger.error(f"Error storing data: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/api/messages', methods=['GET'])
def get_messages():
    conn = None
    try:
        # Get query parameters
        limit = request.args.get('limit', default=100, type=int)
        offset = request.args.get('offset', default=0, type=int)
        sender = request.args.get('sender')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Build query based on parameters
        query = "SELECT * FROM messages"
        params = []
        
        if sender:
            query += " WHERE sender = %s"
            params.append(sender)
        
        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cur.execute(query, params)
        messages = cur.fetchall()
        
        return jsonify({
            "status": "success",
            "count": len(messages),
            "messages": messages
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving messages: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/view-messages')
def view_messages():
    try:
        limit = request.args.get('limit', default=50, type=int)
        
        # Get messages from API endpoint
        messages_response = get_messages()
        if messages_response[1] != 200:
            return render_template('error.html', error="Failed to fetch messages")
        
        messages_data = messages_response[0].get_json()
        if messages_data['status'] != 'success':
            return render_template('error.html', error=messages_data['message'])
            
        return render_template('messages.html', 
                             messages=messages_data['messages'],
                             limit=limit)
            
    except Exception as e:
        logger.error(f"Error in view_messages: {e}")
        return render_template('error.html', error=str(e))

@app.route('/')
def index():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get counts for dashboard
        cur.execute("SELECT COUNT(*) FROM data_entries")
        data_count = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM messages")
        message_count = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(DISTINCT profile_username) FROM messages")
        profile_count = cur.fetchone()['count']
        
        return render_template('index.html',
                            data_count=data_count,
                            message_count=message_count,
                            profile_count=profile_count)
        
    except Exception as e:
        logger.error(f"Error in index: {e}")
        return render_template('error.html', error=str(e))
    finally:
        if conn:
            cur.close()
            conn.close()

# Create templates directory if it doesn't exist
os.makedirs('templates', exist_ok=True)

# HTML Templates
with open('templates/index.html', 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Operator Service Monitor</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .dashboard-card {
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .stat-number {
            font-size: 2.5rem;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h1 class="mb-4">Operator Service Monitor</h1>
        
        <div class="row">
            <div class="col-md-4">
                <div class="dashboard-card bg-primary text-white">
                    <h3>Data Entries</h3>
                    <div class="stat-number">{{ data_count }}</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="dashboard-card bg-success text-white">
                    <h3>Messages</h3>
                    <div class="stat-number">{{ message_count }}</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="dashboard-card bg-info text-white">
                    <h3>Profiles</h3>
                    <div class="stat-number">{{ profile_count }}</div>
                </div>
            </div>
        </div>
        
        <div class="mt-4">
            <a href="/view-messages" class="btn btn-primary">View Messages</a>
            <a href="/api/messages" class="btn btn-secondary">API Endpoint</a>
        </div>
    </div>
</body>
</html>
""")

with open('templates/messages.html', 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Operator Service Messages</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .message {
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .user-message {
            background-color: #e6f7ff;
            border-left: 4px solid #1890ff;
        }
        .profile-message {
            background-color: #f6f6f6;
            border-left: 4px solid #666;
        }
        .message-header {
            font-weight: bold;
            margin-bottom: 5px;
        }
        .message-time {
            font-size: 0.8em;
            color: #666;
            float: right;
        }
        .message-content {
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h1 class="mb-4">Operator Service Messages</h1>
        
        <div class="mb-3">
            <form class="row g-3">
                <div class="col-auto">
                    <label for="limit" class="col-form-label">Messages to show:</label>
                </div>
                <div class="col-auto">
                    <input type="number" class="form-control" id="limit" name="limit" value="{{ limit }}" min="1" max="500">
                </div>
                <div class="col-auto">
                    <button type="submit" class="btn btn-primary">Update</button>
                </div>
            </form>
        </div>
        
        <div id="messages-container">
            {% for msg in messages %}
            <div class="message {% if msg.sender == 'user' %}user-message{% else %}profile-message{% endif %}">
                <div class="message-header">
                    {% if msg.sender == 'user' %}User{% else %}{{ msg.profile_username }}{% endif %}
                    <span class="message-time">
                        {{ msg.timestamp|datetimeformat if msg.timestamp else msg.received_at|datetimeformat }}
                    </span>
                </div>
                <div class="message-content">
                    {{ msg.content }}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
""")

with open('templates/error.html', 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Error</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <div class="alert alert-danger">
            <h1>Error</h1>
            <p>{{ error }}</p>
            <a href="/" class="btn btn-primary">Return to Dashboard</a>
        </div>
    </div>
</body>
</html>
""")

# Custom template filter for datetime formatting
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M:%S'):
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime(format)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
