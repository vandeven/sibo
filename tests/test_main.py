import os
import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app, handle_user_command, parse_city_and_meal_type
from pdf_generator import generate_sibo_pdf

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["python_version"] == "3.14.7"
    assert data["deployment"] == "google-cloud-run-buildpacks"


def test_parse_city_and_meal_type():
    """Test parsing user input queries into city and optional meal type."""
    city, meal = parse_city_and_meal_type("Wageningen Italian")
    assert city == "Wageningen"
    assert meal == "Italian"

    city, meal = parse_city_and_meal_type("Amsterdam")
    assert city == "Amsterdam"
    assert meal is None


def test_handle_user_commands():
    """Test slash command handling logic."""
    assert "Running on Python 3.14.7" in handle_user_command("/start", "John")
    assert "Available Commands" in handle_user_command("/help", "John")
    assert "Healthy" in handle_user_command("/status", "John")
    assert "Echo test" in handle_user_command("Echo test", "John")


def test_telegram_webhook_unauthorized(monkeypatch):
    """Test secret token validation header."""
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret_123")

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": 1, "first_name": "TestUser"},
            "chat": {"id": 1, "type": "private"},
            "text": "/start",
        },
    }

    # Wrong token
    res_forbidden = client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "invalid_secret"},
    )
    assert res_forbidden.status_code == 403

    # Correct token
    res_ok = client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret_123"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json() == {"status": "ok"}


def test_pdf_generation():
    """Test rendering PDF report using fpdf2."""
    mock_data = {
        "city": "Wageningen",
        "query_meal_type": "Italian",
        "top_rating": [
            {
                "name": "Trattoria Test",
                "rating": "4.8/5",
                "price_level": "EUR 20 avg",
                "address": "Hoogstraat 1, Wageningen",
                "sibo_meals": [
                    {
                        "meal_name": "Gluten-Free Risotto",
                        "price": "EUR 16.50",
                        "sibo_rationale": "Made with vegetable broth without garlic or onion.",
                        "waiter_instructions": "Specify no garlic or onion in broth."
                    }
                ]
            }
        ],
        "top_price": []
    }

    pdf_path = generate_sibo_pdf(mock_data)
    assert os.path.exists(pdf_path)
    assert pdf_path.endswith(".pdf")
    # Clean up generated test file
    os.remove(pdf_path)
