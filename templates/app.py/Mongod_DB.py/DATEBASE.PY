from pymongo import MongoClient
import certifi
import os

client = MongoClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
db = client["stock_dashboard"]
users = db["users"]