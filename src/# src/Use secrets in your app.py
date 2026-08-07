# src/app.py
from secret_manager import get_api_key

# Instead of reading from .env:
# ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_KEY')

# Now use Secret Manager:
ALPHA_VANTAGE_KEY = get_api_key('OZ6F4UA8NO2SILLV')