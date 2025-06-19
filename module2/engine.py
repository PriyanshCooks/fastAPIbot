import os
import json
import logging
import requests
from typing import List, Optional, Tuple
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pymongo import MongoClient
from pymongo.collection import Collection

# ------------------ Logging ------------------
logging.basicConfig(
    filename='log.txt',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ------------------ Environment Variables ------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
MONGODB_URL = os.getenv("MONGODB_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")


assert OPENAI_API_KEY, "Missing OpenAI API Key!"
assert GOOGLE_PLACES_API_KEY, "Missing Google Places API Key!"
assert MONGODB_URL, "Missing MongoDB URL!"

# ------------------ MongoDB Utilities ------------------
def get_mongo_collection() -> Collection:
    client = MongoClient(MONGODB_URL)
    db = client[MONGO_DB_NAME]
    return db[MONGO_COLLECTION_NAME]

# ------------------ Pydantic Models ------------------
class ConversationEntry(BaseModel):
    question: str
    answer: str

class ConversationLog(BaseModel):
    conversation: List[ConversationEntry]

class PredictionResult(BaseModel):
    predicted_interests: List[str] = Field(..., description=" inferred industries or niches")

class DisplayName(BaseModel):
    text: Optional[str] = None

class Location(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class Place(BaseModel):
    displayName: Optional[DisplayName] = None
    formattedAddress: Optional[str] = None
    location: Optional[Location] = None
    primaryType: Optional[str] = None
    types: Optional[List[str]] = None
    businessStatus: Optional[str] = None
    googleMapsURL: Optional[str] = None
    websiteURL: Optional[str] = None
    nationalPhoneNumber: Optional[str] = None
    internationalPhoneNumber: Optional[str] = None
    rating: Optional[float] = None
    userRatingCount: Optional[int] = Field(None, alias="userRatingCount")

class SearchQueryEntry(BaseModel):
    application: str
    google_search_terms: List[str]
    matched_places: List[Place]
    status: str  # "OK", "ZERO_RESULTS", or "ERROR"

class SearchQueryResults(BaseModel):
    extracted_applications: List[str]
    targeting_keywords: List[SearchQueryEntry]

# ------------------ MongoDB Access ------------------
def get_mongo_client():
    return MongoClient(MONGODB_URL)

def fetch_latest_session_from_mongo() -> Optional[List[ConversationEntry]]:
    client = get_mongo_client()
    db = client["chatbot_db"]  # explicitly use the correct DB
    collection = db["chat_sessions"]  # explicitly use the correct collection

    latest_session = collection.find_one(sort=[("_id", -1)])
    if not latest_session or "messages" not in latest_session:
        return None

    messages = latest_session["messages"]
    qa_pairs = []

    for i in range(0, len(messages) - 1):
        current = messages[i]
        next_msg = messages[i + 1]
        if current["role"] == "assistant" and next_msg["role"] == "user":
            qa_pairs.append(ConversationEntry(
                question=current.get("question", "") or current.get("answer", ""),  # fallback to 'answer' for assistant prompts
                answer=next_msg.get("answer", "")
            ))

    return qa_pairs if qa_pairs else None


# ------------------ Utility Functions ------------------
def json_to_chatml(conversation_log: ConversationLog) -> str:
    chatml_lines = []
    for entry in conversation_log.conversation:
        chatml_lines.append(f"<|user|> {entry.question}")
        chatml_lines.append(f"<|assistant|> {entry.answer}")
    return "\n".join(chatml_lines)

def extract_user_location(conversation_entries: List[ConversationEntry]) -> Optional[str]:
    """
    Very simple heURLstic-based location extraction from user's conversation.
    Looks for any answer that mentions a location clearly.
    """
    import re
    location_keywords = ["location", "city", "region", "area", "place", "from", "based in"]

    for entry in reversed(conversation_entries):  # Search from latest to earliest
        for keyword in location_keywords:
            if keyword in entry.question.lower() or keyword in entry.answer.lower():
                # Extract a proper noun (capitalized word) after the keyword
                match = re.search(rf"{keyword}\s+(in\s+)?([A-Z][a-zA-Z\s]+)", entry.answer)
                if match:
                    return match.group(2).strip()
    return None

def get_lat_lng_from_location(location_name: str) -> Optional[Tuple[float, float]]:
    """
    Uses Google Geocoding API to get lat/lng for a location name
    """
    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": location_name,
        "key": GOOGLE_PLACES_API_KEY
    }
    try:
        response = requests.get(geocode_url, params=params, timeout=10)
        data = response.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception as e:
        logging.error(f"Error in geocoding location '{location_name}': {e}")
    return None

def search_google_places(query: str, location: Optional[Tuple[float, float]] = None, radius: int = 50000) -> Tuple[List[dict], str]:
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": ",".join([
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.primaryType",
            "places.types",
            "places.businessStatus",
            "places.googleMapsUri",
            "places.websiteUri",
            "places.nationalPhoneNumber",
            "places.internationalPhoneNumber",
            "places.rating",
            "places.userRatingCount"
        ])
    }

    payload = {
        "textQuery": query,
        "maxResultCount": 20
    }

    if location:
        lat, lng = location

        # Define a bounding box around the location
        delta = 0.5  # roughly ~50 km radius (tweak if needed)
        min_lat = lat - delta
        max_lat = lat + delta
        min_lng = lng - delta
        max_lng = lng + delta

        payload["locationRestriction"] = {
            "rectangle": {
                "minLatitude": min_lat,
                "maxLatitude": max_lat,
                "minLongitude": min_lng,
                "maxLongitude": max_lng
            }
        }





    all_results = []
    try:
        for _ in range(3):  # Max 3 pages
            response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
            data = response.json()

            places = data.get("places", [])
            all_results.extend(places)

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

            import time
            time.sleep(2)
            payload["pageToken"] = next_page_token

    except Exception as e:
        logging.error(f"Google Places API Exception | Query: '{query}' | Exception: {e}")
        return all_results, "ERROR"

    return all_results, "OK"

# ------------------ Main ------------------
def main():
    conversation_entries = fetch_latest_session_from_mongo()
    if not conversation_entries:
        print("No valid session or qa_items found.")
        return

    conv_log = ConversationLog(conversation=conversation_entries)
    chatml_conversation = json_to_chatml(conv_log)

    user_location = extract_user_location(conversation_entries)
    coords = get_lat_lng_from_location(user_location) if user_location else None
    if coords:
        logging.info(f"User location: {user_location} → {coords}")

    application_prompt = f"""
    You are given a ChatML conversation about a product. Your task is to extract ONLY extremely specific, product-level, real-world application areas of the product discussed.

    EXTREMELY STRICT GUIDELINES:
    - ONLY include granular, concrete use-cases — specific physical products or engineered processes where the product plays a direct, technical role.
    - DO NOT mention any industry (e.g., automotive, medical, packaging, etc.).
    - DO NOT include any vague functional benefits (e.g., "improves strength", "enhances adhesion", "boosts resistance", "improves performance").
    - For each output, specify the *exact application, **target component or material, and **the functional role of the product*.

    VALID EXAMPLES:
    - "adhesion promoter in polypropylene/glass fiber composite bumpers for injection molding"
    - "compatibilizer in recycled polyethylene/polypropylene multilayer film extrusion"
    - "coupling agent for polypropylene/hemp fiber biocomposites used in outdoor decking tiles"
    - "reactive modifier in polypropylene-based filaments for fused deposition modeling (FDM) 3D printing"

    INSTRUCTIONS:
    - Include applications where the product is used as an intermediary or in combination with other products.
    - Include both established and plausible, unexplored applications based on research or product databases.
    - Strictly Include at least 20 granular, product-level applications, output as many as possible, but DO NOT fill the list with generic, business, or industry terms.
    - Output ONLY a comma-separated list of unique, granular, product-level applications. No explanations, no generic terms, no duplicates, no industry or business phrases.

    {chatml_conversation}
    """
    agent = Agent("openai:gpt-3.5-turbo")

    # Stage 1: Application Extraction
    result = agent.run_sync(application_prompt, output_type=PredictionResult)
    applications = result.output.predicted_interests

    # Stage 2: Search per application
    search_results = []
    for app in applications:
        search_prompt = f"""
        You are a B2B technical sales researcher.

        APPLICATION: {app}

        TASK:
        Generate atleast 20 highly effective Google search phrases as possible to find companies, manufacturers, OEMs, or research labs involved in this application. Focus on the material, process, and functional role.

        USE THESE GUIDELINES:
        - Include modifiers like: "supplier", "manufacturer", "OEM", "compounder"
        - Focus only on search terms that would be effective on Google.

        FORMAT:
        Return ONLY a list like this:
        ["<search 1>", "<search 2>", "<search 3>", "<search 4>"]
        """
        try:
            search_result = agent.run_sync(search_prompt, output_type=List[str])
            search_terms = search_result.output
        except Exception as e:
            logging.error(f"Search term error for '{app}': {e}")
            search_terms = []

        all_places = []
        final_status = "ZERO_RESULTS"
        for term in search_terms:
            places, status = search_google_places(term, location=coords)
            if status == "OK" and places:
                final_status = "OK"
            elif status == "ERROR":
                final_status = "ERROR"
            all_places.extend(places)

        unique_places = {}
        for place in all_places:
            if place.get("businessStatus") != "CLOSED_PERMANENTLY":
                place_id = place.get("id")
                if place_id and place_id not in unique_places:
                    unique_places[place_id] = place

        search_results.append(SearchQueryEntry(
            application=app,
            google_search_terms=search_terms,
            matched_places=[Place(**p) for p in unique_places.values()],
            status=final_status
        ))

    final_output = SearchQueryResults(
        extracted_applications=applications,
        targeting_keywords=search_results
    )

    print(final_output.model_dump_json(indent=2))
    with open('output.json', 'w', encoding='utf-8') as f:
        f.write(final_output.model_dump_json(indent=2))
            
    client = MongoClient(MONGODB_URL)
    db = client[MONGO_DB_NAME]
    collection = db[MONGO_COLLECTION_NAME]

    for app_block in final_output.targeting_keywords:
        application_name = app_block.application
        search_terms = app_block.google_search_terms
        matched_places = app_block.matched_places

        doc = {
            "application": application_name,
            "search_terms": search_terms,
            "companies": []
        }

        for company in matched_places:
            company_info = {
                "name": company.displayName.text if company.displayName else None,
                "address": company.formattedAddress,
                "location": {
                    "latitude": company.location.latitude if company.location else None,
                    "longitude": company.location.longitude if company.location else None
                },
                "phone": {
                    "national": company.nationalPhoneNumber,
                    "international": company.internationalPhoneNumber,
                },
                "website": company.websiteURL,
                "google_maps_url": company.googleMapsURL,
                "rating": company.rating,
                "user_rating_count": company.userRatingCount,
                "types": company.types or [],
                "status": company.businessStatus
            }
            doc["companies"].append(company_info)

        # Insert or update into MongoDB
        collection.update_one(
            {"application": application_name},
            {"$set": doc},
            upsert=True
        )

    print(" Data successfully inserted/updated into MongoDB Atlas.")
