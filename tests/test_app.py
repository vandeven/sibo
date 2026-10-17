import platform

import pytest
from fastapi.testclient import TestClient

from sibo_bot.app import SearchService, create_app
from sibo_bot.config import settings
from sibo_bot.models import SearchQuery
from sibo_bot.rate_limit import Cooldown
from sibo_bot.research import ResearchError

from conftest import FakeResearcher, FakeTelegram

SECRET = "secret_123"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "allowed_telegram_user_ids", "")


@pytest.fixture
def telegram():
    return FakeTelegram()


@pytest.fixture
def researcher(city_report):
    return FakeResearcher(report=city_report)


@pytest.fixture
def client(telegram, researcher):
    app = create_app(researcher=researcher, telegram=telegram, cooldown=Cooldown(30))
    with TestClient(app) as c:
        yield c


def post(client, message: dict, secret: str = SECRET):
    message = {"chat": {"id": 1}, "from": {"id": 1, "first_name": "Sam"}, **message}
    return client.post(
        "/telegram/webhook",
        json={"update_id": 1, "message": message},
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "healthy"
    assert data["python_version"] == platform.python_version()


def test_rejects_invalid_secret(client, telegram):
    assert post(client, {"text": "/start"}, secret="wrong").status_code == 403
    assert telegram.messages == []


def test_command_reply(client, telegram):
    res = post(client, {"text": "/start"})
    assert res.status_code == 200 and res.json() == {"status": "ok"}
    assert "Hello Sam" in telegram.messages[0][1]


def test_whitelist_blocks_unknown_user(client, telegram, researcher, monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_user_ids", "42, 43")
    post(client, {"text": "Amsterdam"})
    assert "Access denied" in telegram.messages[0][1]
    assert researcher.queries == []


def test_city_search_sends_pdf(client, telegram, researcher):
    post(client, {"text": "Wageningen Italian"})
    assert researcher.queries == [SearchQuery(city="Wageningen", cuisine="Italian")]
    (chat_id, pdf, filename, caption), = telegram.documents
    assert pdf.startswith(b"%PDF-")
    assert filename == "SIBO_Guide_Wageningen.pdf"


def test_location_search(client, researcher):
    post(client, {"location": {"latitude": 51.97, "longitude": 5.66}})
    assert researcher.queries == [SearchQuery(latitude=51.97, longitude=5.66)]


def test_rate_limit(client, telegram, researcher):
    post(client, {"text": "Utrecht"})
    post(client, {"text": "Utrecht"})
    assert len(researcher.queries) == 1
    assert "Please wait" in telegram.messages[-1][1]


async def test_research_error_is_reported_without_internals(telegram):
    service = SearchService(FakeResearcher(error=ResearchError("Service busy.")), telegram)
    await service.run(1, SearchQuery(city="Delft"))
    assert telegram.messages[-1][1] == "❌ Service busy."


async def test_unexpected_error_is_hidden(telegram):
    service = SearchService(FakeResearcher(error=RuntimeError("secret stack detail")), telegram)
    await service.run(1, SearchQuery(city="Delft"))
    assert "secret stack detail" not in telegram.messages[-1][1]
    assert "Something went wrong" in telegram.messages[-1][1]
