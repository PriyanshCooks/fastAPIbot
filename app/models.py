from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base  # Correct import of Base

class ChatSession(Base):
    __tablename__ = "chat_session"

    id = Column(Integer, primary_key=True, index=True)
    session_uuid = Column(String(64), unique=True, nullable=False)
    # Back_populates to link with QAItem
    qa_items = relationship(
        "QAItem",
        back_populates="chat_session",
        cascade="all, delete-orphan"
    )

class QAItem(Base):
    __tablename__ = "qa_item"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(Integer, ForeignKey("chat_session.id"), nullable=False)
    role = Column(String(10), nullable=False)  # "assistant" or "user"
    question = Column(Text, default="")
    answer = Column(Text, default="")

    # Link back to parent ChatSession
    chat_session = relationship("ChatSession", back_populates="qa_items")
