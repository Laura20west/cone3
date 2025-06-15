from flask import Flask, request, jsonify
import json
import random
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import pipeline, AutoModelForSeq2SeqLM, AutoTokenizer
import os
from datetime import datetime
import sqlite3
from collections import deque

app = Flask(__name__)

# Configuration
DATABASE_FILE = "conversations.db"
LOG_FILE = "conversation_logs.json"
MAX_DATASET_SIZE = 10000

# Initialize database
def initialize_database():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_message TEXT NOT NULL,
            bot_response TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def load_conversation_dataset():
    """Load conversation history from database into memory"""
    dataset = deque(maxlen=MAX_DATASET_SIZE)
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_message, bot_response 
            FROM conversations 
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (MAX_DATASET_SIZE,))
        
        # Add in chronological order (oldest first)
        for row in reversed(cursor.fetchall()):
            dataset.append(row)
            
        conn.close()
        print(f"Loaded {len(dataset)} conversation pairs into memory")
    except Exception as e:
        print(f"Error loading conversation dataset: {str(e)}")
    
    return dataset

def initialize_models():
    try:
        paraphrase_model = pipeline(
            "text2text-generation", 
            model="tuner007/pegasus_paraphrase",
            device=0 if os.getenv('USE_GPU') == '1' else -1
        )
        return paraphrase_model
    except Exception as e:
        print(f"Error initializing paraphrase model: {str(e)}")
        return None

# Initialize everything at startup
initialize_database()
conversation_dataset = load_conversation_dataset()
paraphrase_model = initialize_models()

# Helper functions
def find_best_match(user_input):
    """Find the best matching conversation pair using TF-IDF and cosine similarity"""
    if not conversation_dataset:
        return None, None
    
    # Extract user messages from dataset
    user_messages = [pair[0] for pair in conversation_dataset]
    
    # Vectorize messages
    vectorizer = TfidfVectorizer(stop_words='english')
    try:
        tfidf_matrix = vectorizer.fit_transform(user_messages)
    except ValueError:  # Happens if all messages are empty
        return None, None
    
    # Calculate similarities
    query_vec = vectorizer.transform([user_input])
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
    
    # Find top matches
    top_indices = similarities.argsort()[-5:][::-1]  # Top 5 matches
    
    if not top_indices.size:
        return None, None
    
    # Select a random top match
    chosen_idx = random.choice(top_indices)
    return conversation_dataset[chosen_idx]

def paraphrase_response(response):
    """Paraphrase the response using Pegasus model"""
    if not paraphrase_model:
        return response
    
    try:
        paraphrases = paraphrase_model(
            response,
            max_length=60,
            num_return_sequences=1,
            num_beams=5
        )
        if paraphrases and 'generated_text' in paraphrases[0]:
            return paraphrases[0]['generated_text']
    except Exception as e:
        print(f"Error paraphrasing response: {str(e)}")
    
    return response

def log_conversation(session_id, user_message, bot_response):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations 
            (session_id, user_message, bot_response)
            VALUES (?, ?, ?)
        ''', (session_id, user_message, bot_response))
        
        conn.commit()
        conn.close()
        
        # Add to in-memory dataset
        conversation_dataset.append((user_message, bot_response))
        
        # Log to JSON file
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "user_message": user_message,
            "bot_response": bot_response
        }
        
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
        return True
    except Exception as e:
        print(f"Error logging conversation: {str(e)}")
        return False

# API Endpoints
@app.route('/chat', methods=['POST'])
def chat():
    # Get request data
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "Missing message in request"}), 400
    
    user_message = data['message']
    session_id = data.get('session_id', "default_session")
    
    # Find best matching conversation pair
    matched_pair = find_best_match(user_message)
    
    if matched_pair:
        _, orig_bot_response = matched_pair
        paraphrased_response = paraphrase_response(orig_bot_response)
    else:
        paraphrased_response = "I'm still learning. Could you tell me more about that?"
    
    # Log the conversation
    log_conversation(session_id, user_message, paraphrased_response)
    
    # Prepare response
    response = {
        "response": paraphrased_response,
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }
    
    return jsonify(response)

@app.route('/conversations', methods=['GET'])
def get_conversations():
    try:
        # Get query parameters
        limit = request.args.get('limit', default=100, type=int)
        session_id = request.args.get('session_id')
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        query = "SELECT * FROM conversations"
        params = []
        
        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        conversations = cursor.fetchall()
        
        # Convert to list of dicts
        columns = [column[0] for column in cursor.description]
        result = [dict(zip(columns, row)) for row in conversations]
        
        conn.close()
        
        return jsonify({"conversations": result})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
