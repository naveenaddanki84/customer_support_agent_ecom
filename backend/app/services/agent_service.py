"""Assistant identity (name + welcome message)."""

from app.app_config import app_config


def agent_info() -> dict:
    name = app_config.agent_name
    return {
        "name": name,
        "welcome": (
            f"Hi! I'm {name}, your virtual support assistant. I can help with orders, "
            f"refunds, and general questions. How can I help you today?"
        ),
    }
