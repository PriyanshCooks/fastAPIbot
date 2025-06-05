# create_db.py
from app.db import Base, engine
import app.models  # just import models so metadata is loaded

def create_database():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")

if __name__ == "__main__":
    create_database()
