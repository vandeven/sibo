import pytest
from pydantic import ValidationError

from sibo_bot.models import SearchQuery
from sibo_bot.telegram import LOCATION_KEYBOARD
from sibo_bot.version import APP_VERSION
from sibo_bot.updates import PENDING_CUISINE_TTL_SECONDS, IncomingMessage, MessageRouter, Reply, parse_update


def text_msg(text: str) -> IncomingMessage:
    return IncomingMessage(chat_id=1, user_id=1, first_name="Sam", text=text)


def location_msg() -> IncomingMessage:
    return IncomingMessage(chat_id=1, user_id=1, first_name="Sam", latitude=51.97, longitude=5.66)


def test_search_query_from_text():
    assert SearchQuery.from_text("Wageningen Italian") == SearchQuery(city="Wageningen", cuisine="Italian")
    assert SearchQuery.from_text("  Amsterdam ") == SearchQuery(city="Amsterdam")
    assert SearchQuery.from_text("Rotterdam gluten free pizza").cuisine == "gluten free pizza"


def test_search_query_requires_city_or_coordinates():
    with pytest.raises(ValidationError):
        SearchQuery()
    with pytest.raises(ValidationError):
        SearchQuery(latitude=1.0)
    with pytest.raises(ValidationError):
        SearchQuery(latitude=100.0, longitude=5.0)


def test_parse_update_text_and_location():
    text = parse_update({"message": {"chat": {"id": 7}, "from": {"id": 9, "first_name": "Ann"}, "text": " Utrecht "}})
    assert text == IncomingMessage(chat_id=7, user_id=9, first_name="Ann", text="Utrecht")

    loc = parse_update({"message": {"chat": {"id": 7}, "from": {"id": 9}, "location": {"latitude": 52.1, "longitude": 5.1}}})
    assert (loc.latitude, loc.longitude) == (52.1, 5.1)


@pytest.mark.parametrize(
    "payload",
    [{}, {"message": {"chat": {"id": 1}}}, {"message": {"text": "hi"}}, {"message": {"chat": {"id": 1}, "sticker": {}}}],
)
def test_parse_update_ignores_irrelevant(payload):
    assert parse_update(payload) is None


def test_route_city_search():
    assert MessageRouter().route(text_msg("Wageningen Italian")) == SearchQuery(city="Wageningen", cuisine="Italian")


def test_route_location_search_without_cuisine():
    assert MessageRouter().route(location_msg()) == SearchQuery(latitude=51.97, longitude=5.66)


def test_near_command_remembers_cuisine_for_next_location():
    router = MessageRouter()
    reply = router.route(text_msg("/near sushi"))
    assert isinstance(reply, Reply)
    assert reply.reply_markup == LOCATION_KEYBOARD
    assert router.route(location_msg()).cuisine == "sushi"
    assert router.route(location_msg()).cuisine is None  # consumed


def test_near_cuisine_expires():
    now = [0.0]
    router = MessageRouter(clock=lambda: now[0])
    router.route(text_msg("/near sushi"))
    now[0] = PENDING_CUISINE_TTL_SECONDS + 1
    assert router.route(location_msg()).cuisine is None


def test_commands():
    router = MessageRouter()
    start = router.route(text_msg("/start"))
    assert "Hello Sam" in start.html and start.reply_markup == LOCATION_KEYBOARD
    assert "How to use me" in router.route(text_msg("/help@SiboBot")).html
    assert "healthy" in router.route(text_msg("/status")).html
    assert "How to use me" in router.route(text_msg("/unknown")).html


@pytest.mark.parametrize("text", ["version", "Version", "/version", "/version@SiboBot"])
def test_version_reply(text):
    reply = MessageRouter().route(text_msg(text))
    assert isinstance(reply, Reply) and APP_VERSION in reply.html


def test_user_text_is_html_escaped():
    msg = IncomingMessage(chat_id=1, user_id=1, first_name="<b>x</b>", text="/start")
    assert "&lt;b&gt;x&lt;/b&gt;" in MessageRouter().route(msg).html
