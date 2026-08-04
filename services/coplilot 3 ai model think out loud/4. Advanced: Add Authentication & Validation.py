# app.py with authentication
from flask import Flask, jsonify, request, abort
from functools import wraps
import jwt
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/model', methods=['GET'])
@token_required
def get_model():
    return jsonify({
        'version': '1.0.0',
        'status': 'active',
        'last_updated': datetime.datetime.now().isoformat()
    })

@app.route('/api/model/predict', methods=['POST'])
@token_required
def make_prediction():
    data = request.get_json()

    # Input validation
    if not data or 'features' not in data:
        return jsonify({'error': 'Missing features'}), 400

    features = data['features']
    if not isinstance(features, list):
        return jsonify({'error': 'Features must be a list'}), 400

    # Your prediction logic here
    prediction = sum(features) / len(features)  # Example logic

    return jsonify({
        'prediction': prediction,
        'features': features
    })