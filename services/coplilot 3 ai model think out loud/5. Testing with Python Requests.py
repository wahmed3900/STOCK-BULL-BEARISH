import requests
import json

BASE_URL = "http://localhost:5000"

# Test GET
def test_get_model():
    response = requests.get(f"{BASE_URL}/api/model")
    print(f"GET Response: {response.json()}")

# Test POST prediction
def test_predict():
    data = {"features": [1.2, 3.4, 5.6, 7.8]}
    response = requests.post(
        f"{BASE_URL}/api/model/predict",
        json=data,
        headers={"Content-Type": "application/json"}
    )
    print(f"Prediction Response: {response.json()}")

if __name__ == "__main__":
    test_get_model()
    test_predict()