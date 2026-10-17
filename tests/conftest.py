import pytest

from sibo_bot.models import Dish, Restaurant, RestaurantReport


class FakeTelegram:
    def __init__(self, document_ok: bool = True):
        self.messages: list[tuple[int, str, dict | None]] = []
        self.documents: list[tuple[int, bytes, str, str | None]] = []
        self._document_ok = document_ok

    async def send_message(self, chat_id, html_text, reply_markup=None):
        self.messages.append((chat_id, html_text, reply_markup))
        return True

    async def send_document(self, chat_id, content, filename, caption=None):
        self.documents.append((chat_id, content, filename, caption))
        return self._document_ok

    async def aclose(self):
        pass


class FakeResearcher:
    def __init__(self, report=None, error: Exception | None = None):
        self.queries = []
        self._report = report
        self._error = error

    async def research(self, query):
        self.queries.append(query)
        if self._error:
            raise self._error
        return self._report


def make_restaurant(name: str, distance_km: float | None = None) -> Restaurant:
    return Restaurant(
        name=name,
        address="Hoogstraat 42, Wageningen",
        rating="4.8/5",
        price_level="moderate (mains €18-25)",
        distance_km=distance_km,
        dishes=[
            Dish(
                name="Risotto ai Funghi",
                price="€18.50",
                why_sibo_friendly="Arborio rice is low-FODMAP once mushrooms are swapped out.",
                modifications=["No garlic or onion in the broth", "Swap mushrooms for zucchini"],
            ),
            Dish(name="Grilled sea bass", price="€22", why_sibo_friendly="Plain fish with potatoes.", modifications=[]),
        ],
    )


@pytest.fixture
def city_report() -> RestaurantReport:
    return RestaurantReport(
        location_label="Wageningen",
        cuisine="Italian",
        top_rated=[make_restaurant("Trattoria Da Luigi"), make_restaurant("Café Ünïcode ✓")],
        cheapest=[],
    )


@pytest.fixture
def location_report() -> RestaurantReport:
    return RestaurantReport(
        location_label="Wageningen, Centrum",
        top_rated=[make_restaurant("Osteria Vicina", distance_km=0.4)],
        cheapest=[make_restaurant("Snackbar Budget", distance_km=1.7)],
        notes="Radius widened to 3 km to find enough options.",
    )
