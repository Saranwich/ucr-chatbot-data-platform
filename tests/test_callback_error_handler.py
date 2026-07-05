"""The webhook must never leave the user staring at silence.

When handling an event blows up, `handle_event_safely` should catch it and send
a friendly "try again" reply — and if that rescue reply also fails, it must NOT
crash the request.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from linebot.v3.webhooks import MessageEvent

import app.routes.line as line
from app.config import SYSTEM_ERROR_TEXT


def _event():
    e = MagicMock(spec=MessageEvent)
    e.reply_token = "tok"
    return e


def test_emergency_reply_sent_when_handler_raises(monkeypatch):
    monkeypatch.setattr(line, "route_message_event",
                        AsyncMock(side_effect=RuntimeError("boom")))
    bot = MagicMock()
    bot.reply_message = AsyncMock()

    asyncio.run(line.handle_event_safely(_event(), bot, None))

    bot.reply_message.assert_awaited_once()
    sent = bot.reply_message.await_args.args[0]
    assert sent.reply_token == "tok"
    assert sent.messages[0].text == SYSTEM_ERROR_TEXT


def test_failing_rescue_does_not_crash(monkeypatch):
    monkeypatch.setattr(line, "route_message_event",
                        AsyncMock(side_effect=RuntimeError("boom")))
    bot = MagicMock()
    bot.reply_message = AsyncMock(side_effect=RuntimeError("line down"))

    # must not raise even though both the handler AND the rescue fail
    asyncio.run(line.handle_event_safely(_event(), bot, None))
    bot.reply_message.assert_awaited_once()


def test_no_emergency_reply_on_success(monkeypatch):
    monkeypatch.setattr(line, "route_message_event", AsyncMock())
    bot = MagicMock()
    bot.reply_message = AsyncMock()

    asyncio.run(line.handle_event_safely(_event(), bot, None))

    line.route_message_event.assert_awaited_once()
    bot.reply_message.assert_not_awaited()  # the wrapper sends nothing on success
