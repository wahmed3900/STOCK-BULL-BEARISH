import os
import requests

# Add this to your Config class block
class Config:
    HF_TOKEN = os.environ.get('HUGGINGFACE_TOKEN', '')

# Quick utility function to verify your token connection parameters
def verify_hf_token():
    if not Config.HF_TOKEN:
        print("[-] Warning: Hugging Face token is missing from your .env configuration.")
        return False
        
    headers = {"Authorization": f"Bearer {Config.HF_TOKEN}"}
    response = requests.get("https://huggingface.co", headers=headers)
    
    if response.status_code == 200:
        print(f"[+] Hugging Face connection validated securely for user: {response.json().get('username')}")
        return True
    else:
        print("[-] Error: Handshake rejected. Invalid or expired Hugging Face token.")
        return False
