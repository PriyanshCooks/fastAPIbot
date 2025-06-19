#app/schemas.py
'''from pydantic import BaseModel
from typing import List, Optional

# --- Used when creating a new QAItem ---
class QAItemCreate(BaseModel):
    role: str  # "user" or "assistant"
    question: Optional[str] = ""
    answer: Optional[str] = ""

# --- Used when creating a new ChatSession ---
class ChatSessionCreate(BaseModel):
    session_uuid: str
    qa_items: List[QAItemCreate]

# --- Response for individual QA items ---
class QAItemResponse(QAItemCreate):
    id: int

    class Config:
        from_attributes = True  # Pydantic v2+

# --- Response for full chat session with all QA items ---
class ChatSessionResponse(BaseModel):
    id: int
    session_uuid: str
    qa_items: List[QAItemResponse]

    class Config:
        from_attributes = True

# --- Used for /chat/sessions summary endpoint ---
class QAItemSummary(BaseModel):
    role: str
    question: str
    answer: str

    class Config:
        from_attributes = True

class ChatSessionSummary(BaseModel):
    session_uuid: str
    qa_items: List[QAItemSummary]

    class Config:
        from_attributes = True

# --- Request schema for /chat/ask endpoint ---
class ChatAskRequest(BaseModel):
    session_uuid: str
    question: str

# --- Response schema for /chat/ask endpoint ---
class ChatAskResponse(BaseModel):
    answer: str'''