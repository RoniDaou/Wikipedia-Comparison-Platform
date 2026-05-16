"""
Configuration settings for the Wikipedia Infobox Tool
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    # MongoDB Configuration
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'wikipedia_infobox')
    
    # Flask Configuration
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    
    # Scraping Configuration
    REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', 1.0))  # Delay between requests in seconds
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    TIMEOUT = int(os.getenv('TIMEOUT', 10))
    
    # Comparison Configuration
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.6))