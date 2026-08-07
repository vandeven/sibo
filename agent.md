# SIBO Telegram Bot & Restaurant PDF Generator - Agent Notes

## Overview
Automated Telegram bot service hosted on Google Cloud Run. The bot accepts Telegram messages containing a target **City** and optional **Meal Type / Cuisine**, sends an immediate confirmation back to the user in English, instructs Gemini (`gemini-2.0-flash`) to perform Google Search Grounding for SIBO-friendly restaurants, formats the findings into a structured PDF report, and sends the PDF back via Telegram.

---

## Technical Specifications & Stack

- **Language / Runtime**: Python `3.13.1` (configured via `.python-version` / runtime environment for GCP Buildpack).
- **Deployment Platform**: Google Cloud Run using Google Cloud Buildpacks.
- **Cloud Run Authentication Setting**: `--allow-unauthenticated` at the GCP IAM level (required because Telegram Bot API cannot generate Google Cloud IAM identity tokens). Security is enforced at the Application Level via Secret Tokens and User Whitelisting.
- **Default Language**: English (PDF reports and Telegram notification messages).
- **Environment Configuration & Secrets**: Standard Cloud Run Environment Variables:
  - `TELEGRAM_BOT_TOKEN`: Token issued by Telegram @BotFather.
  - `GEMINI_API_KEY`: Key for Gemini API with Google Search Grounding enabled.
  - `TELEGRAM_WEBHOOK_SECRET`: Secret token for webhook validation (`X-Telegram-Bot-Api-Secret-Token`).
  - `ALLOWED_TELEGRAM_USER_IDS`: Comma-separated list of allowed Telegram user IDs for multi-user access (e.g. `"123456789,987654321,555444333"`).
- **Trigger / Ingress**: Telegram Bot API Webhook endpoint (`HTTP POST /webhook/{secret_path}`).
- **LLM Engine**: `gemini-2.0-flash` via official `google-genai` SDK with mandatory Web Search grounding (`google_search`).
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
   - If unauthorized, drop or return `403/200` without triggering Gemini or PDF generation, preventing API quota abuse.

4. **Rate Limiting & Throttling**:
   - Implement simple per-user or global rate limiting (e.g., maximum 1 PDF research request per user every 30 seconds) to avoid spam/looping expenses.

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
- **Specific Meal / Cuisine Specified**: If the user suggests a specific meal type or cuisine (e.g., *"sushi"*, *"Italian"*, *"breakfast"*), Gemini will search for locations in the target city serving that specific type of meal and find SIBO-friendly options within that menu.
- **Unspecified / General Query**: If no specific meal type is specified (e.g., user only sends *"Wageningen"*), Gemini will evaluate entire menus across all top restaurants in the city for SIBO-friendly dishes.

### Output Structure (2 Rankings)
The PDF report must always present two distinct top-5 lists regardless of whether a specific meal type was requested:
1. **Top 5 Best Restaurants by Rating**
2. **Top 5 Best Restaurants by Price**

### Required Information per Restaurant
Each restaurant listing in both top-5 sections must include:
- **Restaurant Name**
- **Average Price / Price Level**
- **SIBO-Friendly Meals**: Specific dishes matching the query (or best menu matches if general query).
- **Meal Prices**: Price for each recommended SIBO-friendly meal.
- **SIBO Rationale & Waiter Instructions**: Detailed explanation of why the item is SIBO-friendly, including precise substitution or modification instructions to tell the waiter (e.g., *"Ask for no garlic, onion, or high-FODMAP sauces; request olive oil and lemon dressing instead"*).

---

## End-to-End Execution Flow

1. **Telegram Ingress (Webhook & Validation)**:
   - Receives Telegram message payload (verifies `X-Telegram-Bot-Api-Secret-Token` and sender ID against whitelisted IDs).
   - Extracts `chat_id`, `city`, and optional `meal_type`.
   - Immediately sends a confirmation message to the user via Telegram (`sendMessage`):  
     > *"🔍 Researching SIBO-friendly restaurants in {city}{' for ' + meal_type if meal_type else ''}... Generating your PDF report now!"*
   - Responds `HTTP 200 OK` to Telegram within timeout window.

2. **Async Research & Gemini Search Grounding**:
   - Executes Gemini `gemini-2.0-flash` request with Google Search Grounding enabled (`tools=[{"google_search": {}}]`).
   - Prompts Gemini to return structured JSON matching the SIBO restaurant criteria (Top 5 by Rating & Top 5 by Price).

3. **PDF Generation (`fpdf2`)**:
   - Formats the JSON response into a clean, modern PDF document in English with structured headings, tables/cards, and clear waiter instruction callouts.

4. **Telegram Document Delivery**:
   - Sends the generated PDF report to the user's `chat_id` using `sendDocument`.
   - Cleans up temporary PDF files.
