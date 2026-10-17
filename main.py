"""ASGI entrypoint for the Procfile / Cloud Run: `uvicorn main:app`."""

import logging

from sibo_bot.app import create_app

logging.basicConfig(level=logging.INFO)

app = create_app()
