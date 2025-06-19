from pymongo import MongoClient
import certifi
from datetime import datetime
from typing import Optional, List, Dict
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Get URI from environment
MONGO_URL = os.getenv("MONGO_URL")
if not MONGO_URL:
    raise RuntimeError("MONGO_URL not found in environment variables")

# MongoDB client
client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
db = client["chatbot_db"]
collection = db["chat_sessions"]

def store_message(session_uuid: str, question: str, answer: str, role: Optional[str] = "user") -> None:
    message = {
        "question": question,
        "answer": answer,
        "timestamp": datetime.now(),
        "role": role
    }

    if collection.find_one({"session_uuid": session_uuid}):
        collection.update_one(
            {"session_uuid": session_uuid},
            {"$push": {"messages": message}}
        )
    else:
        collection.insert_one({
            "session_uuid": session_uuid,
            "messages": [message],
            "created_at": datetime.now()
        })

def get_chat_session(session_uuid: str) -> Optional[Dict]:
    return collection.find_one({"session_uuid": session_uuid})

def get_qa_history(session_uuid: str) -> List[Dict]:
    session = collection.find_one({"session_uuid": session_uuid})
    return session.get("messages", []) if session else []
