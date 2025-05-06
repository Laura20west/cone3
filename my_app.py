from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import spacy
import json
from datetime import datetime
from pathlib import Path
import uuid
import random
from collections import defaultdict, deque
import nltk
from nltk.corpus import wordnet as wn
from typing import Dict, List, Optional
from collections import Counter

# Initialize NLP
nlp = spacy.load("en_core_web_md")
nltk.download('wordnet')

app = FastAPI()

# Configuration
DATASET_PATH = Path("conversation_dataset.jsonl")
UNCERTAIN_PATH = Path("uncertain_responses.jsonl")
REPLY_POOLS_PATH = Path("reply_pools_augmented.json")

# Track used responses and questions
USED_RESPONSES = defaultdict(set)
USED_QUESTIONS = defaultdict(set)

# Load or initialize reply pools
if REPLY_POOLS_PATH.exists():
    with open(REPLY_POOLS_PATH, "r") as f:
        REPLY_POOLS = json.load(f)
    # Ensure all categories have required fields
    for category in REPLY_POOLS.values():
        category.setdefault("triggers", [])
        category.setdefault("responses", [])
        category.setdefault("questions", [])
else:
    REPLY_POOLS = {
        "general": {
            "triggers": [],
            "responses": ["Honey, let's talk about something more exciting..."],
            "questions": ["What really gets you going?"]
        }
    }

# Initialize response queues
CATEGORY_QUEUES = {}
for category, data in REPLY_POOLS.items():
    responses = data["responses"]
    questions = data["questions"]
    combinations = [(r_idx, q_idx) for r_idx in range(len(responses)) 
                   for q_idx in range(len(questions))]
    random.shuffle(combinations)
    CATEGORY_QUEUES[category] = deque(combinations)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

class UserMessage(BaseModel):
    message: str

class SallyResponse(BaseModel):
    matched_word: str
    matched_category: str
    confidence: float
    replies: List[str]

def log_to_dataset(user_input: str, response_data: dict):
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "matched_category": response_data["matched_category"],
        "response": response_data["replies"][0] if response_data["replies"] else None,
        "question": response_data["replies"][1] if len(response_data["replies"]) > 1 else None,
        "confidence": response_data["confidence"],
        "embedding": nlp(user_input).vector.tolist()
    }
    
    with open(DATASET_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def store_uncertain(user_input: str):
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "reviewed": False
    }
    
    with open(UNCERTAIN_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def augment_dataset():
    if not DATASET_PATH.exists():
        return
    
    with open(DATASET_PATH, "r") as f:
        entries = [json.loads(line) for line in f]
    
    category_counts = defaultdict(int)
    for entry in entries:
        category_counts[entry["matched_category"]] += 1
    
    avg_count = sum(category_counts.values()) / len(category_counts) if category_counts else 0
    needs_augmentation = [k for k, v in category_counts.items() if v < avg_count * 0.5]
    
    for category in needs_augmentation:
        if category not in REPLY_POOLS:
            continue
            
        base_triggers = REPLY_POOLS[category]["triggers"]
        new_triggers = []
        
        for trigger in base_triggers:
            doc = nlp(trigger)
            lemmatized = " ".join([token.lemma_ for token in doc])
            new_triggers.append(lemmatized)
            
            for token in doc:
                if token.pos_ in ["NOUN", "VERB"]:
                    syns = [syn.lemmas()[0].name() for syn in wn.synsets(token.text)]
                    if syns:
                        new_triggers.append(trigger.replace(token.text, syns[0]))
        
        REPLY_POOLS[category]["triggers"] = list(set(REPLY_POOLS[category]["triggers"] + new_triggers))
    
    with open(REPLY_POOLS_PATH, "w") as f:
        json.dump(REPLY_POOLS, f, indent=2)
    
    # Reinitialize queues after augmentation
    global CATEGORY_QUEUES
    CATEGORY_QUEUES = {}
    for category, data in REPLY_POOLS.items():
        responses = data["responses"]
        questions = data["questions"]
        combinations = [(r_idx, q_idx) for r_idx in range(len(responses)) 
                       for q_idx in range(len(questions))]
        random.shuffle(combinations)
        CATEGORY_QUEUES[category] = deque(combinations)

def get_best_match(doc):
    best_match = ("general", None, 0.0)
    
    # Enhanced matching with multiple strategies
    for category, data in REPLY_POOLS.items():
        # Strategy 1: Full phrase similarity
        for trigger in data["triggers"]:
            trigger_doc = nlp(trigger)
            similarity = doc.similarity(trigger_doc)
            if similarity > best_match[2]:
                best_match = (category, trigger, similarity)
        
        # Strategy 2: Token-level matching with POS consideration
        for token in doc:
            if token.pos_ in ["NOUN", "VERB", "ADJ"]:  # Focus on meaningful words
                for trigger in data["triggers"]:
                    if token.lemma_ in trigger.lower():
                        current_sim = 0.7 + (0.3 * (token.pos_ == "NOUN"))  # Nouns get higher weight
                        if current_sim > best_match[2]:
                            best_match = (category, token.text, current_sim)
    
    # Strategy 3: WordNet synonym expansion
    if best_match[2] < 0.7:  # If confidence is low
        for token in doc:
            if token.pos_ in ["NOUN", "VERB"]:
                synsets = wn.synsets(token.text)
                for syn in synsets:
                    for lemma in syn.lemmas():
                        for category, data in REPLY_POOLS.items():
                            if lemma.name() in data["triggers"]:
                                current_sim = 0.65  # Slightly lower confidence for synonyms
                                if current_sim > best_match[2]:
                                    best_match = (category, lemma.name(), current_sim)
    
    return best_match

def get_unique_response_pair(category):
    category_data = REPLY_POOLS[category]
    responses = category_data["responses"]
    questions = category_data["questions"]
    
    # Find unused response-question pairs
    available_responses = [i for i in range(len(responses)) if i not in USED_RESPONSES[category]]
    available_questions = [i for i in range(len(questions)) if i not in USED_QUESTIONS[category]]
    
    if available_responses and available_questions:
        # Try to find a fresh pair
        for r_idx in available_responses:
            for q_idx in available_questions:
                return (r_idx, q_idx)
    
    # If no fresh pairs, reset used sets and try again
    if not available_responses:
        USED_RESPONSES[category].clear()
        available_responses = list(range(len(responses)))
    if not available_questions:
        USED_QUESTIONS[category].clear()
        available_questions = list(range(len(questions)))
    
    if available_responses and available_questions:
        r_idx = random.choice(available_responses)
        q_idx = random.choice(available_questions)
        return (r_idx, q_idx)
    
    # Fallback if still no pairs found
    return (0, 0) if responses and questions else (None, None)

@app.post("/1C9I6F1O5R1C8O3N87E5145ID", response_model=SallyResponse)
async def analyze_message(user_input: UserMessage):
    message = user_input.message.strip()
    doc = nlp(message.lower())
    
    best_match = get_best_match(doc)
    
    # Prepare response
    response = {
        "matched_word": best_match[1] or "general",
        "matched_category": best_match[0],
        "confidence": round(best_match[2], 2),
        "replies": []
    }
    
    # Get non-repeating response pair
    category_data = REPLY_POOLS[best_match[0]]
    if category_data["responses"] and category_data["questions"]:
        r_idx, q_idx = get_unique_response_pair(best_match[0])
        
        if r_idx is not None and q_idx is not None:
            response["replies"].append(category_data["responses"][r_idx])
            response["replies"].append(category_data["questions"][q_idx])
            USED_RESPONSES[best_match[0]].add(r_idx)
            USED_QUESTIONS[best_match[0]].add(q_idx)
    
    # Fallback if no responses found
    if not response["replies"]:
        response["replies"] = [
            "Honey, let's take this somewhere more private...",
            "What's your deepest, darkest fantasy?"
        ]
    
    # Log interaction
    log_to_dataset(message, response)
    
    # Active learning
    if response["confidence"] < 0.6:
        store_uncertain(message)
        if len(response["replies"]) > 1:
            response["replies"][1] += " Could you rephrase that, baby?"
    
    return response

@app.get("/dataset/analytics")
async def get_analytics():
    analytics = {
        "total_entries": 0,
        "common_categories": {},
        "confidence_stats": {}
    }
    
    if DATASET_PATH.exists():
        with open(DATASET_PATH, "r") as f:
            entries = [json.loads(line) for line in f]
        
        analytics["total_entries"] = len(entries)
        analytics["common_categories"] = Counter(entry["matched_category"] for entry in entries)
        
        if entries:
            confidences = [entry["confidence"] for entry in entries]
            analytics["confidence_stats"] = {
                "average": round(sum(confidences)/len(confidences), 2),
                "min": round(min(confidences), 2),
                "max": round(max(confidences), 2)
            }
    
    return analytics

@app.post("/augment")
async def trigger_augmentation():
    augment_dataset()
    return {"status": "Dataset augmented", "new_pools": REPLY_POOLS}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)