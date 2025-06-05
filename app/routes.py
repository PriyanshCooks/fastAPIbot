from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import uuid

from .db import get_db
from .models import ChatSession, QAItem
from .gpt import ask_openai

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_chat_session(db: Session, session_uuid: str):
    return db.query(ChatSession).filter(ChatSession.session_uuid == session_uuid).first()

def create_chat_session(db: Session):
    session_uuid = str(uuid.uuid4())
    new_session = ChatSession(session_uuid=session_uuid)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

def get_qa_history(db: Session, chat_session: ChatSession):
    return db.query(QAItem).filter(QAItem.chat_session_id == chat_session.id).order_by(QAItem.id).all()

def build_history(qa_items):
    history = []
    for item in qa_items:
        if item.role == "assistant":
            history.append({"role": "assistant", "content": item.question})
        elif item.role == "user":
            history.append({"role": "user", "content": item.answer})
    return history

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        chat_session = create_chat_session(db)
        request.session["chat_uuid"] = chat_session.session_uuid
    else:
        chat_session = get_chat_session(db, session_uuid)
        if not chat_session:
            chat_session = create_chat_session(db)
            request.session["chat_uuid"] = chat_session.session_uuid

    qa_items = get_qa_history(db, chat_session)
    if not qa_items:
        first_question = "What is your product and what does it do?"
        assistant_qa = QAItem(chat_session_id=chat_session.id, role="assistant", question=first_question)
        db.add(assistant_qa)
        db.commit()
        db.refresh(assistant_qa)
        qa_items = get_qa_history(db, chat_session)
    else:
        assistant_items = [item for item in qa_items if item.role == "assistant"]
        user_items = [item for item in qa_items if item.role == "user"]
        if len(user_items) < len(assistant_items):
            first_question = assistant_items[len(user_items)].question
        else:
            first_question = assistant_items[-1].question if assistant_items else "What is your product and what does it do?"

    return templates.TemplateResponse("index.html", {"request": request, "question": first_question, "qa_log": qa_items})

@router.post("/", response_class=HTMLResponse)
async def post_answer(request: Request, answer: str = Form(...), db: Session = Depends(get_db)):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        return RedirectResponse(url="/", status_code=303)

    chat_session = get_chat_session(db, session_uuid)
    if not chat_session:
        chat_session = create_chat_session(db)
        request.session["chat_uuid"] = chat_session.session_uuid

    qa_items = get_qa_history(db, chat_session)
    history = build_history(qa_items)

    user_answer = answer.strip()
    if user_answer == "":
        assistant_items = [item for item in qa_items if item.role == "assistant"]
        user_items = [item for item in qa_items if item.role == "user"]
        if len(user_items) < len(assistant_items):
            last_question = assistant_items[len(user_items)].question
        else:
            last_question = "What is your product and what does it do?"
        return templates.TemplateResponse("index.html", {"request": request, "question": last_question, "qa_log": qa_items})

    user_qa = QAItem(chat_session_id=chat_session.id, role="user", question="", answer=user_answer)
    db.add(user_qa)
    db.commit()

    qa_items = get_qa_history(db, chat_session)
    history.append({"role": "user", "content": user_answer})

    assistant_questions_count = db.query(QAItem).filter(QAItem.chat_session_id == chat_session.id, QAItem.role == "assistant").count()
    if assistant_questions_count >= 10:
        return RedirectResponse(url="/complete", status_code=303)

    next_question = ask_openai(
        "Based on the previous Q&A, ask the next most relevant question strictly related to understanding"
        " the user’s product, its logistics, buyer requirements, and supply-readiness."
        " You must cover all 4 of these before the 10th question if not already covered:"
        " Turnaround Time, Supply Capacity, Present Demand, Expected Demand."
        " Do NOT ask about market trends or insights. Do NOT ask for user’s analysis of the market."
        " Ask only what the user would realistically know and what helps find customers."
        " Avoid redundancy.",
        history,
        qa_items,
    )

    assistant_qa = QAItem(chat_session_id=chat_session.id, role="assistant", question=next_question, answer="")
    db.add(assistant_qa)
    db.commit()

    qa_items = get_qa_history(db, chat_session)

    return templates.TemplateResponse("index.html", {"request": request, "question": next_question, "qa_log": qa_items})

@router.get("/complete", response_class=HTMLResponse)
async def complete(request: Request, db: Session = Depends(get_db)):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        return HTMLResponse("No conversation found.", status_code=404)

    chat_session = get_chat_session(db, session_uuid)
    if not chat_session:
        return HTMLResponse("No conversation found.", status_code=404)

    qa_items = get_qa_history(db, chat_session)
    return templates.TemplateResponse("complete.html", {"request": request, "qa_log": qa_items})
