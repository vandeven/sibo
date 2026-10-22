# SIBO Telegram Bot & Restaurant PDF Generator - Agent Notes

## Overview
Automated Telegram bot service hosted on Google Cloud Run. The bot accepts Telegram messages containing a target **City** and optional **Meal Type / Cuisine**, or a shared **Telegram location** (optionally preceded by `/near <cuisine>`), sends an immediate confirmation back to the user in English, asks Claude (`claude-sonnet-5-5` by default, with the server-side web search tool and structured outputs) to research SIBO-friendly restaurants, formats the findings into a structured PDF report, and sends the PDF back via Telegram.

---

## Technical Specifications & Stack

- **Language / Runtime**: Python `3.13.1` (configured via `.python-version` / runtime environment for GCP Buildpack).
- **Deployment Platform**: Google Cloud Run using Google Cloud Buildpacks.
- **Cloud Run Authentication Setting**: `--allow-unauthenticated` at the GCP IAM level (required because Telegram Bot API cannot generate Google Cloud IAM identity tokens). Security is enforced at the Application Level via Secret Tokens and User Whitelisting.
- **Default Language**: English (PDF reports and Telegram notification messages).
- **Environment Configuration & Secrets**: Standard Cloud Run Environment Variables:
  - `TELEGRAM_BOT_TOKEN`: Token issued by Telegram @BotFather.
  - `ANTHROPIC_API_KEY`: Claude API key.
  - Optional: `CLAUDE_MODEL` (default `claude-sonnet-5-5`), `CLAUDE_EFFORT` (default `medium`), `WEB_SEARCH_MAX_USES` (default 8), `SEARCH_RADIUS_KM` (default 2), `RATE_LIMIT_SECONDS` (default 30).
  - `TELEGRAM_WEBHOOK_SECRET`: Secret token for webhook validation (`X-Telegram-Bot-Api-Secret-Token`).
  - `ALLOWED_TELEGRAM_USER_IDS`: Comma-separated list of allowed Telegram user IDs for multi-user access (e.g. `"123456789,987654321,555444333"`).
- **Trigger / Ingress**: Telegram Bot API Webhook endpoint (`HTTP POST /telegram/webhook`).
- **LLM Engine**: Claude via the official `anthropic` SDK (`AsyncAnthropic`, streaming, `web_search_20260209` server tool, `output_format=RestaurantReport` structured outputs, server-side refusal fallback).
- **PDF Generation**: `fpdf2` (Pure Python, free, open-source, actively maintained, lightweight with no C/binary system dependencies).
- **Delivery API**: Telegram Bot API HTTP endpoints (`sendMessage` and `sendDocument`).

---

## Endpoint Protection & Security Strategy

### Why Public (Unauthenticated) Ingress on Cloud Run?
Google Cloud Run's native IAM authentication (`--no-allow-unauthenticated`) requires clients to send a Google OIDC Identity Token in the `Authorization` header. Because Telegram's webhook system does not support Google IAM authentication, Cloud Run must be configured to **allow unauthenticated invocations**.

### Application-Level Defense (4 Layers)
Application-level verification ensures only legitimate Telegram requests are processed:

1. **Secret Token Header Verification (`X-Telegram-Bot-Api-Secret-Token`)**:
   - When registering the webhook via Telegram `setWebhook`, pass a secret token (`secret_token`).
   - Telegram attaches header `X-Telegram-Bot-Api-Secret-Token` to every POST request.
   - App checks this header against `TELEGRAM_WEBHOOK_SECRET`. Reject requests failing matching with `403 Forbidden` immediately before parsing JSON.

2. **Secret Webhook URL Path**:
   - Use a secret UUID in the URL path (e.g. `POST /webhook/a8f3b2e9-7c1d-4e5f-901a-2b3c4d5e6f7a`).
   - Only Telegram knows this URL, preventing discovery via port scanning or generic URL probing.

3. **Multi-User Telegram ID Whitelisting (Access Control)**:
   - Extract `message.from.id` or `message.chat.id` from payload.
   - Verify ID against the set of allowed IDs parsed from `ALLOWED_TELEGRAM_USER_IDS` (supports multiple comma-separated IDs).
   - If unauthorized, drop or return `403/200` without triggering Claude or PDF generation, preventing API quota abuse.

4. **Rate Limiting & Throttling**:
   - In-memory per-user cooldown (`sibo_bot/rate_limit.py`, default 1 search per 30 seconds per Cloud Run instance).

---

## Health Check & Dynamic Version Tracking
The `/health` endpoint dynamically returns:
- `status`: `"healthy"`
- `version`: Application semantic version (e.g. `"1.0.0"`)
- `commit`: Dynamic Git Commit SHA (retrieved from `COMMIT_SHA` / `K_REVISION` environment variables in Cloud Run, or fallback to local `git rev-parse --short HEAD`)
- `python_version`: Current Python runtime version
- `deployment`: Infrastructure metadata (`google-cloud-run-buildpacks`)

---

## Data & Prompting Requirements

### Dietary Focus
- **SIBO (Small Intestinal Bacterial Overgrowth)** compliant / Low FODMAP / Low Fermentation options.

### Query Flexibility & Matching
- **Specific Meal / Cuisine Specified**: If the user suggests a specific meal type or cuisine (e.g., *"sushi"*, *"Italian"*, *"breakfast"*), Claude will search for locations in the target city serving that specific type of meal and find SIBO-friendly options within that menu.
- **Unspecified / General Query**: If no specific meal type is specified (e.g., user only sends *"Wageningen"*), Claude will evaluate entire menus across all top restaurants in the city for SIBO-friendly dishes.

### Location Search
- Users tap the **📍 Share my location** reply-keyboard button (shown with `/start` and `/help`); Telegram sends `message.location`.
- Claude searches within `SEARCH_RADIUS_KM` of the coordinates, widening only if needed (reported in the PDF notes), and returns `distance_km` per restaurant.
- `/near <cuisine>` stores a cuisine for that chat (10 min TTL) that is applied to the next shared location.

### Output Structure (2 Rankings)
The PDF report must always present two distinct top-5 lists regardless of whether a specific meal type was requested:
1. **Top 5 best-rated restaurants**
2. **Top 5 cheapest restaurants**

### Required Information per Restaurant
Each restaurant listing in both top-5 sections must include:
- **Restaurant Name**
- **Average Price / Price Level**
- **SIBO-Friendly Meals**: Specific dishes matching the query (or best menu matches if general query).
- **Meal Prices**: Price for each recommended SIBO-friendly meal.
- **SIBO Rationale & Waiter Instructions**: Detailed explanation of why the item is SIBO-friendly, including precise substitution or modification instructions to tell the waiter (e.g., *"Ask for no garlic, onion, or high-FODMAP sauces; request olive oil and lemon dressing instead"*).

---

## Code Layout
- `main.py` - ASGI entrypoint (`uvicorn main:app`), calls `sibo_bot.app.create_app()`.
- `sibo_bot/config.py` - settings from env / `.env`.
- `sibo_bot/models.py` - `SearchQuery`, `RestaurantReport`, `Restaurant`, `Dish` (the report doubles as the Claude output schema).
- `sibo_bot/research.py` - Claude prompt and API call (`RestaurantResearcher`, `ResearchError`).
- `sibo_bot/pdf.py` - fpdf2 renderer, returns PDF bytes (no temp files).
- `sibo_bot/telegram.py` - async Telegram Bot API client (HTML parse mode).
- `sibo_bot/updates.py` - parses updates and routes them to command replies or searches.
- `sibo_bot/app.py` - FastAPI routes, webhook auth, background search job.
- `generate_pdf.py` - CLI: `python generate_pdf.py Wageningen Italian` or `--lat 51.97 --lon 5.66 [cuisine]`.
- Tests: `pip install -r requirements-dev.txt && pytest` (live Claude test runs only when `ANTHROPIC_API_KEY` is set).

## End-to-End Execution Flow

1. **Telegram ingress**: verify secret header and whitelist, route the message (command reply, or a city/location `SearchQuery`), apply the cooldown, queue a background job and return `200 OK`.
2. **Research**: send a confirmation, then call Claude with web search; the response is parsed into a validated `RestaurantReport`.
3. **PDF**: render the report with fpdf2 in memory.
4. **Delivery**: send the PDF with `sendDocument`. Errors are logged; users get a friendly message without internals.
