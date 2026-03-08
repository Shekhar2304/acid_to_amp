import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = "sqlite:///acid_to_amp.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
