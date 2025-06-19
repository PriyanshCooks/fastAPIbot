# module2/__init__.py

"""
Module 2: Application Extraction and Company Search

This module is responsible for:
1. Fetching the latest chatbot conversation from MongoDB.
2. Extracting granular product-level application areas using GPT.
3. Generating Google search queries for those applications.
4. Using Google Places API to find relevant companies.
5. Storing the results back into MongoDB.
"""

from .engine import main as run_search_pipeline

