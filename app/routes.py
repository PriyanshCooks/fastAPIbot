# app/routes.py
import threading
from module2 import run_search_pipeline

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import uuid

from datetime import datetime

from .mongo import get_chat_session, get_qa_history, store_message
from .gpt import run_agent, AskInput

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        session_uuid = str(uuid.uuid4())
        request.session["chat_uuid"] = session_uuid
        first_question = "What is your product and what does it do?"
        store_message(session_uuid, first_question, "", role="assistant")
    else:
        session = get_chat_session(session_uuid)
        if not session:
            session_uuid = str(uuid.uuid4())
            request.session["chat_uuid"] = session_uuid
            first_question = "What is your product and what does it do?"
            store_message(session_uuid, first_question, "", role="assistant")
        else:
            messages = session.get("messages", [])
            assistant_messages = [m for m in messages if m["role"] == "assistant"]
            user_messages = [m for m in messages if m["role"] == "user"]

            if len(user_messages) < len(assistant_messages):
                first_question = assistant_messages[len(user_messages)]["question"]
            else:
                first_question = assistant_messages[-1]["question"] if assistant_messages else "What is your product and what does it do?"

    qa_log = get_qa_history(session_uuid)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "question": first_question, "qa_log": qa_log},
    )

def build_history(qa_items):
    history = []
    for item in qa_items:
        if item["role"] == "assistant":
            history.append({"role": "assistant", "content": item["question"]})
        elif item["role"] == "user":
            history.append({"role": "user", "content": item["answer"]})
    return history

@router.post("/", response_class=HTMLResponse)
async def post_answer(
    request: Request,
    answer: Optional[str] = Form(None),
    end_conversation: Optional[str] = Form(None),
):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        return RedirectResponse(url="/", status_code=303)

    session = get_chat_session(session_uuid)
    if not session:
        session_uuid = str(uuid.uuid4())
        request.session["chat_uuid"] = session_uuid
        store_message(session_uuid, "What is your product and what does it do?", "", role="assistant")
        session = get_chat_session(session_uuid)

    qa_log = get_qa_history(session_uuid)

    # ✅ End conversation if button clicked
    if end_conversation == "true":
        store_message(session_uuid, "", "Conversation ended by user.", role="system")
        return RedirectResponse(url="/complete", status_code=303)

    user_answer = answer.strip() if answer else ""

    if user_answer == "":
        assistant_messages = [m for m in qa_log if m["role"] == "assistant"]
        user_messages = [m for m in qa_log if m["role"] == "user"]
        if len(user_messages) < len(assistant_messages):
            last_question = assistant_messages[len(user_messages)]["question"]
        else:
            last_question = "What is your product and what does it do?"
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "question": last_question, "qa_log": qa_log},
        )

    # ✅ Store user response
    store_message(session_uuid, "", user_answer, role="user")

    # ✅ Refresh QA log and history
    qa_log = get_qa_history(session_uuid)
    history = build_history(qa_log)

    assistant_questions_count = len([m for m in qa_log if m["role"] == "assistant"])

    if assistant_questions_count == 14:
        next_question = "Would you like to share anything else about the product which would help us find you even better matches?"
    elif assistant_questions_count >= 15:
        return RedirectResponse(url="/complete", status_code=303)
    else:
        # Ensure all timestamps in qa_log are strings
        for item in qa_log:
            if isinstance(item.get("timestamp"), datetime):
                item["timestamp"] = item["timestamp"].isoformat()
        next_question = run_agent(AskInput(
            prompt="Based on the previous Q&A, ask the next most relevant question strictly related to understanding"
                   " the user’s product, its logistics, buyer requirements, and supply-readiness."
                   " You must cover all 3 of these before the 15th question if not already covered: Turnaround Time, Supply Capacity, Present Demand."
                   " If the user gives a vague answer like 'I don’t know', 'not sure', or leaves it blank, try rephrasing the previous question in a more specific or guided way."
                   " For example, if the question was about technical specifications and the user replied 'I don’t know', then follow up with:"
                   " 'No worries! Would you know the dimensions, materials used, weight, power requirements, or any certifications it has?'"
                   " Always give examples or typical attributes they can comment on."
                   " Do NOT ask about market trends or insights. Do NOT ask for the user’s analysis of the market."
                   " Avoid redundancy, and ask only what the user would realistically know and what helps find customers.",
            history=history,
            qa_items=qa_log
        ))

    store_message(session_uuid, next_question, "", role="assistant")

    qa_log = get_qa_history(session_uuid)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "question": next_question, "qa_log": qa_log},
    )

@router.get("/complete", response_class=HTMLResponse)
async def complete(request: Request):
    session_uuid = request.session.get("chat_uuid")
    if not session_uuid:
        return HTMLResponse("No conversation found.", status_code=404)

    session = get_chat_session(session_uuid)
    if not session:
        return HTMLResponse("No conversation found.", status_code=404)

    qa_log = get_qa_history(session_uuid)

    # ✅ Start Module 2 in the background after chatbot session completes
    def run_module2_background():
        try:
            print("🔍 Module 2 search pipeline started...")
            run_search_pipeline()
            print("✅ Module 2 search pipeline finished.")
        except Exception as e:
            print(f"❌ Error in Module 2 pipeline: {e}")

    threading.Thread(target=run_module2_background).start()

    # ✅ Optionally show search started message
    return templates.TemplateResponse(
        "complete.html", {"request": request, "qa_log": qa_log, "search_started": True}
    )
