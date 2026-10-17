import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from sibo_bot.models import SearchQuery
from sibo_bot.research import ResearchError, RestaurantResearcher, build_user_prompt


class FakeAnthropic:
    """Mimics `client.beta.messages.stream(...)` returning queued responses."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    @asynccontextmanager
    async def _stream(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)

        async def get_final_message():
            return response

        yield SimpleNamespace(get_final_message=get_final_message)


def response(stop_reason="end_turn", parsed=None, content=()):
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, content=list(content), usage=None)


def test_location_prompt_includes_coordinates_and_radius():
    prompt = build_user_prompt(SearchQuery(latitude=51.97, longitude=5.66, cuisine="sushi"), radius_km=2)
    assert "51.97" in prompt and "5.66" in prompt and "2 km" in prompt and "sushi" in prompt


def test_city_prompt():
    prompt = build_user_prompt(SearchQuery(city="Delft"), radius_km=2)
    assert "Delft" in prompt and "No cuisine" in prompt


async def test_research_returns_parsed_report_and_uses_web_search(city_report):
    fake = FakeAnthropic(response(parsed=city_report))
    report = await RestaurantResearcher(client=fake).research(SearchQuery(city="Wageningen"))
    assert report is city_report
    (call,) = fake.calls
    assert call["tools"][0]["type"].startswith("web_search")
    assert call["output_format"].__name__ == "RestaurantReport"


async def test_research_continues_after_pause_turn(city_report):
    paused_content = [SimpleNamespace(type="server_tool_use")]
    fake = FakeAnthropic(response("pause_turn", content=paused_content), response(parsed=city_report))
    assert await RestaurantResearcher(client=fake).research(SearchQuery(city="Delft")) is city_report
    assert fake.calls[1]["messages"][-1] == {"role": "assistant", "content": paused_content}


@pytest.mark.parametrize("stop_reason", ["refusal", "end_turn", "max_tokens"])
async def test_research_without_report_raises(stop_reason):
    fake = FakeAnthropic(response(stop_reason, parsed=None))
    with pytest.raises(ResearchError):
        await RestaurantResearcher(client=fake).research(SearchQuery(city="Delft"))


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
async def test_live_research():
    report = await RestaurantResearcher().research(SearchQuery(city="Wageningen", cuisine="Italian"))
    assert report.top_rated or report.cheapest
