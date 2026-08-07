import pytest
import json
import hmac
import hashlib
from unittest.mock import patch
from app import app, Config

@pytest.fixture
def client():
    """Provides an isolated test client with testing mode activated."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def generate_secure_headers(payload_bytes: bytes) -> dict:
    """Helper method to generate authentic cryptographic security validation blocks."""
    computed_sig = "sha256=" + hmac.new(
        Config.SECRET_KEY.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return {
        "X-Hub-Signature-256": computed_sig,
        "Content-Type": "application/json"
    }

# =============================================================================
#  Behavior Test 1: Bearish Sentiment & Stock Price Drop Parsing
# =============================================================================
@pytest.mark.market_behavior
@patch('app.requests.post')
@patch('app.requests.get')
def test_bearish_market_behavior(mock_get, mock_post, client):
    """Verifies the pipeline handles falling stocks and negative news arrays accurately."""
    
    Config.HF_TOKEN = "hf_active_token_string"

    # Simulate a declining stock price setup
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "Global Quote": {
            "01. symbol": "INTC",
            "05. price": "19.50",
            "06. volume": "89000000"
        }
    }

    # Simulate a highly confident negative classification output from FinBERT
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"label": "negative", "score": 0.9912}

    payload = {"ticker": "INTC", "headline": "Intel drops dividend payouts as manufacturing lines stall."}
    payload_bytes = json.dumps(payload).encode('utf-8')
    headers = generate_secure_headers(payload_bytes)

    response = client.post('/api/v1/market/analyze', data=payload_bytes, headers=headers)
    response_json = json.loads(response.data.decode('utf-8'))

    assert response.status_code == 200
    assert response_json['verdict'] == 'BEARISH'  # Translates negative -> BEARISH
    assert response_json['metric']['price'] == 19.50

# =============================================================================
#  Behavior Test 2: Unresolved API Payloads & Market Trading Halts
# =============================================================================
@pytest.mark.network_failure
@patch('app.requests.get')
@patch('app.db_manager.get_metric')
def test_empty_or_halted_api_payload_fallback(mock_db, mock_get, client):
    """Guarantees the system falls back to database state if Alpha Vantage blanks out."""
    
    # Simulate an empty API or rate-limit message from Alpha Vantage
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"Note": "Thank you for using Alpha Vantage. Rate limit exceeded."}

    # Force database fallback manager to step up with historical data
    mock_db.return_value = {
        "ticker": "TSLA",
        "price": 175.00,
        "pe_ratio": None,
        "market_cap": 0.0,
        "volume": 12000000
    }

    response = client.get('/api/v1/market/ticker/TSLA')
    payload_json = json.loads(response.data.decode('utf-8'))

    assert response.status_code == 200
    assert payload_json['status'] == 'success'
    assert payload_json['data']['price'] == 175.00  # Saved by the database fallback logic!

# =============================================================================
#  Behavior Test 3: Automated Firewall & Malicious Signature Rejection
# =============================================================================
@pytest.mark.security
def test_malicious_signature_firewall_rejection(client):
    """Guarantees that altered payloads or mismatched keys throw a 403 Forbidden."""
    
    payload = {"ticker": "AMZN"}
    payload_bytes = json.dumps(payload).encode('utf-8')
    
    # Intentionally corrupt the headers with an invalid verification token string
    headers = {
        "X-Hub-Signature-256": "sha256=completely_fabricated_signature_string",
        "Content-Type": "application/json"
    }

    response = client.post('/api/v1/market/analyze', data=payload_bytes, headers=headers)
    response_json = json.loads(response.data.decode('utf-8'))

    assert response.status_code == 403
    assert "Invalid verification token" in response_json['error']
