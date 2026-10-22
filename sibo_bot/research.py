import logging

import anthropic
import pydantic

from sibo_bot.config import settings
from sibo_bot.models import RestaurantReport, SearchQuery

logger = logging.getLogger(__name__)

MAX_TOKENS = 32_000
MAX_PAUSE_CONTINUATIONS = 3
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You are a culinary research assistant for people with SIBO (Small Intestinal Bacterial Overgrowth).
You find real restaurants and tell the user exactly what they can order.

Dietary rules (low-FODMAP, low-fermentation):
- Avoid: garlic, onion (incl. powders, shallot, leek bulb), wheat/rye/barley in larger amounts, beans and \
lentils, lactose-heavy dairy, honey, high-fructose fruit, sugar alcohols, inulin/chicory, cauliflower, \
mushrooms, asparagus, large portions of avocado.
- Generally safe: plain grilled/roasted meat, fish and eggs; rice, potatoes, quinoa, oats, gluten-free \
pasta, sourdough spelt; carrots, zucchini, spinach, bell pepper, cucumber, green beans, tomato; hard \
cheeses; olive oil, lemon, fresh herbs, the green part of spring onion, garlic-infused oil.
- Sauces, stocks, marinades and spice rubs are the most common hidden source of garlic and onion.

Research method:
- Use web search to find real, currently operating restaurants with their ratings, price level and menus.
- Only recommend dishes you found on a real menu. Prefer dishes that are safe as served; otherwise give \
the concrete modifications to ask the waiter for (e.g. "no garlic or onion in the sauce; olive oil and \
lemon instead", "swap the bread for rice"). Skip dishes that can't realistically be made safe.
- Give each restaurant 1-3 dishes.

Output:
- top_rated: the 5 best-rated restaurants that have at least one safe or modifiable dish, best first.
- cheapest: the 5 restaurants with the lowest typical main-course price that have at least one safe or \
modifiable dish, cheapest first.
- A restaurant may appear in both lists. Return fewer than 5 only if you truly cannot find more, and \
explain why in notes.
- Give every price in euros (€). If a menu uses another currency, convert it at the current exchange \
rate and mark it approximate with '~' (e.g. '~€12').
- Write everything in English."""


class ResearchError(Exception):
    """Research failed; `user_message` is safe to show to the Telegram user."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def build_user_prompt(query: SearchQuery, radius_km: float) -> str:
    cuisine = (
        f"Focus on restaurants serving {query.cuisine} and SIBO-friendly options within that menu."
        if query.cuisine
        else "No cuisine was specified: consider full menus across all well-reviewed restaurants."
    )
    if query.is_location:
        area = (
            f"Find SIBO-friendly restaurants near latitude {query.latitude}, longitude {query.longitude}. "
            f"Only include restaurants within {radius_km:g} km of that point. If there are fewer than 5 "
            "per list, widen the radius gradually and say so in notes. Set distance_km for every "
            "restaurant and set location_label to the neighbourhood and city of that point."
        )
    else:
        area = f"Find SIBO-friendly restaurants in {query.city}. Set location_label to the city name."
    return f"{area}\n{cuisine}"


class RestaurantResearcher:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        self._client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)

    async def research(self, query: SearchQuery) -> RestaurantReport:
        user_prompt = build_user_prompt(query, settings.search_radius_km)
        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        web_search = {"type": "web_search_20260209", "name": "web_search", "max_uses": settings.web_search_max_uses}

        try:
            for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
                async with self._client.beta.messages.stream(
                    model=settings.claude_model,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=[web_search],
                    output_config={"effort": settings.claude_effort},
                    output_format=RestaurantReport,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                ) as stream:
                    response = await stream.get_final_message()

                if response.stop_reason != "pause_turn":
                    break
                # Server-side web search hit its iteration limit; resend so Claude can continue.
                messages = [messages[0], {"role": "assistant", "content": response.content}]
        except anthropic.RateLimitError as e:
            logger.warning("Claude rate limited: %s", e)
            raise ResearchError("The research service is busy right now. Please try again in a minute.") from e
        except anthropic.APIConnectionError as e:
            logger.error("Could not reach the Claude API: %s", e)
            raise ResearchError("Could not reach the research service. Please try again later.") from e
        except pydantic.ValidationError as e:
            logger.error("Claude returned a report that does not match the schema: %s", e)
            raise ResearchError("The research came back incomplete. Please try again.") from e
        except anthropic.APIStatusError as e:
            logger.error("Claude API error %s (request %s): %s", e.status_code, e.request_id, e.message)
            raise ResearchError("The research service returned an error. Please try again later.") from e

        logger.info("Claude research done: stop_reason=%s usage=%s", response.stop_reason, response.usage)

        if response.stop_reason == "refusal":
            raise ResearchError("The request was declined by the research service. Try a different query.")
        report = response.parsed_output
        if report is None:
            raise ResearchError("The research came back incomplete. Please try again.")
        return report
