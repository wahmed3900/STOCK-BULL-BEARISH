import os
import tempfile
from unittest.mock import patch

import pytest

from src.app import app as flask_app


@pytest.fixture
def client():
    temp_dir = tempfile.mkdtemp(prefix="stock-dashboard-test-", dir="/tmp")
    db_path = os.path.join(temp_dir, "subscriptions.db")
    flask_app.config.update(TESTING=True, DATABASE_PATH=db_path)
    flask_app.config.pop("DATABASE_FILE", None)

    with flask_app.app_context():
        from src import app as app_module
        app_module.init_db()

    with flask_app.test_client() as client:
        yield client


def test_registration_and_login(client):
    response = client.post(
        "/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    assert response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    assert login_response.status_code == 200
    payload = login_response.get_json()
    assert payload["user"]["username"] == "alice"
    assert payload["user"]["plan"] == "free"


def test_free_plan_limits_batch_analysis(client):
    client.post(
        "/auth/register",
        json={"username": "bob", "password": "secret123"},
    )
    client.post(
        "/auth/login",
        json={"username": "bob", "password": "secret123"},
    )

    with patch("src.app.analyze_stock", return_value=({"ticker": "AAPL"}, None)):
        response = client.post(
            "/analyze/batch",
            json={"tickers": ["AAPL", "MSFT", "GOOG", "TSLA"]},
        )

    assert response.status_code == 403
    payload = response.get_json()
    assert "free plan" in payload["message"].lower()
