import json
import logging
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a SIBO (Small Intestinal Bacterial Overgrowth) culinary research assistant.
Your task is to find restaurants in a given city that offer SIBO-friendly (low-FODMAP, low-fermentation) food options.

IMPORTANT RULES:
1. ALWAYS perform web searches to find real, existing restaurants, current ratings, average prices, and menu items.
2. Provide TWO distinct top-5 lists:
   - "top_rating": Top 5 best restaurants by rating (highest customer satisfaction/reviews)
   - "top_price": Top 5 best restaurants by price (most budget-friendly / best value)
3. For each restaurant, list specific SIBO-friendly meals (or dishes that can be modified to be SIBO-friendly).
4. For each SIBO meal, include:
   - Meal name
   - Estimated price
   - Explanation of why it is SIBO-friendly (e.g. low-FODMAP ingredients, gluten-free/lactose-free)
   - Specific, polite waiter instructions (e.g. "Ask for no garlic, onion, or wheat; request olive oil dressing").
5. Return ONLY a valid JSON object matching the exact JSON structure specified below. Do not wrap in markdown code blocks if possible, or ensure it parses cleanly as JSON.

REQUIRED JSON FORMAT:
{
  "city": "City Name",
  "query_meal_type": "Meal Type or 'General Menu'",
  "top_rating": [
    {
      "name": "Restaurant Name",
      "rating": "4.7/5",
      "price_level": "€€ (€15-25 avg)",
      "address": "123 Main St, City",
      "sibo_meals": [
        {
          "meal_name": "Dish Name",
          "price": "€14.50",
          "sibo_rationale": "Grilled salmon with rice and steamed zucchini; naturally low FODMAP.",
          "waiter_instructions": "Request no garlic, onion, or butter sauce; ask for lemon and olive oil on the side."
        }
      ]
    }
  ],
  "top_price": [
    {
      "name": "Restaurant Name",
      "rating": "4.3/5",
      "price_level": "€ (€8-15 avg)",
      "address": "45 Market Ave, City",
      "sibo_meals": [
        {
          "meal_name": "Dish Name",
          "price": "€9.00",
          "sibo_rationale": "Simple rice bowl with plain chicken breast and spinach.",
          "waiter_instructions": "Specify no onion powder or garlic seasoning on chicken."
        }
      ]
    }
  ]
}
"""


def research_sibo_restaurants(city: str, meal_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Invokes Gemini with Google Search Grounding to research SIBO-friendly restaurants.
    Returns structured dictionary with top_rating and top_price lists.
    """
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not configured.")

    client = genai.Client(api_key=settings.gemini_api_key)

    meal_query = f" serving {meal_type}" if meal_type else ""
    user_prompt = (
        f"Search for top SIBO-friendly (low FODMAP) restaurants in {city}{meal_query}.\n"
        f"Identify the top 5 restaurants by rating and top 5 by price in {city}.\n"
        f"If a specific meal type ('{meal_type}') is specified, search for restaurants serving that dish/cuisine. "
        f"If no meal type is specified, search across full menus of top restaurants in {city}.\n"
        f"Return the research results strictly as the requested JSON object."
    )

    candidate_models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.5-pro"]
    last_error = None

    for model_name in candidate_models:
        try:
            logger.info(f"Attempting Gemini search grounding with model: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                )
            )

            text_content = response.text.strip()
            # Clean markdown formatting if present
            if text_content.startswith("```json"):
                text_content = text_content[7:]
            if text_content.startswith("```"):
                text_content = text_content[3:]
            if text_content.endswith("```"):
                text_content = text_content[:-3]
            text_content = text_content.strip()

            data = json.loads(text_content)
            return data

        except Exception as e:
            logger.warning(f"Gemini model '{model_name}' failed: {e}. Trying fallback...")
            last_error = e

    logger.error(f"All Gemini candidate models failed. Last error: {last_error}")
    return {
        "city": city,
        "query_meal_type": meal_type or "General Menu",
        "top_rating": [],
        "top_price": [],
        "error": str(last_error)
    }
