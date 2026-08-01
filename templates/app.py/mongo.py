from pymongo import MongoClient
import certifi

uri = uri = "mongodb+srv://stockapp:tVIqKPfb8zj3rd2F@cluster0.nhs6fqc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(uri, tlsCAFile=certifi.where())
try:
    client.admin.command('ping')
    print("✅ Connected successfully!")
except Exception as e:
    print("❌ Connection failed:", e)