import asyncio
from unittest.mock import AsyncMock, MagicMock

from linebot.v3.webhooks import (
    TextMessageContent,
    LocationMessageContent,
    ImageMessageContent,
)

import app.handlers.message_handler as mh
from app.handlers.message_handler import route_message_event


def _event_with(content_cls):
    """A fake MessageEvent whose .message passes isinstance(content_cls)."""
    event = MagicMock()
    event.message = MagicMock(spec=content_cls)
    return event


def _spy_downstream(monkeypatch):
    """Replace the three downstream handlers with spies; return them."""
    spies = {
        "handle_text_message": AsyncMock(),
        "handle_chatbot_location": AsyncMock(),
        "handle_chatbot_image": AsyncMock(),
    }
    for name, spy in spies.items():
        monkeypatch.setattr(mh, name, spy)
    return spies


def test_text_message_routes_to_text_handler(monkeypatch):
    spies = _spy_downstream(monkeypatch)
    asyncio.run(route_message_event(_event_with(TextMessageContent), None, None))
    spies["handle_text_message"].assert_awaited_once()
    spies["handle_chatbot_location"].assert_not_awaited()
    spies["handle_chatbot_image"].assert_not_awaited()


def test_location_message_routes_to_chatbot_location(monkeypatch):
    spies = _spy_downstream(monkeypatch)
    asyncio.run(route_message_event(_event_with(LocationMessageContent), None, None))
    spies["handle_chatbot_location"].assert_awaited_once()
    spies["handle_text_message"].assert_not_awaited()
    spies["handle_chatbot_image"].assert_not_awaited()


def test_image_message_routes_to_chatbot_image(monkeypatch):
    spies = _spy_downstream(monkeypatch)
    asyncio.run(route_message_event(_event_with(ImageMessageContent), None, None))
    spies["handle_chatbot_image"].assert_awaited_once()
    spies["handle_text_message"].assert_not_awaited()
    spies["handle_chatbot_location"].assert_not_awaited()
