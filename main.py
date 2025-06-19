from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
from app.routes import router as chatbot_router

# Load environment variables from .env
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Session middleware for storing session UUIDs
app.add_middleware(SessionMiddleware, secret_key=os.getenv("FASTAPI_SECRET_KEY", "supersecretkey"))

# Mount static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template directory
templates = Jinja2Templates(directory="templates")

# Import and include routes
app.include_router(chatbot_router)
