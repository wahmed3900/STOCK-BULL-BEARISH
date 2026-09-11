# src/secret_manager.py
import os
import json
from google.cloud import secretmanager

def get_secret(secret_id, project_id=None):
    """
    Access secret from Google Secret Manager
    """
    if project_id is None:
        # Get project ID from environment
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            raise ValueError("Project ID not found. Set GOOGLE_CLOUD_PROJECT environment variable.")
    
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    
    try:
        response = client.access_secret_version(request={"name": name})
        secret_string = response.payload.data.decode("UTF-8")
        return secret_string
    except Exception as e:
        print(f"Error accessing secret {secret_id}: {e}")
        return None

# Usage example for your stock dashboard
def get_api_key(service_name):
    """
    Get API key for a specific service
    """
    secret_map = {
        'alpha_vantage': 'alpha-vantage-key',
        'polygon': 'polygon-api-key',
        'finnhub': 'finnhub-key',
        'docker': 'docker-hub-password'
    }
    
    secret_id = secret_map.get(service_name)
    if not secret_id:
        raise ValueError(f"No secret configured for {service_name}")
    
    return get_secret(secret_id)

# In your main app:
if __name__ == "__main__":
    # Use it like this:
    alpha_vantage_key = get_api_key('alpha_vantage')
    print("API Key retrieved successfully!")