"""Regression: step advance must be atomic with the reply being sent.

Bug: process_survey_answer committed the step advance BEFORE sending the next
question. On a poor connection the reply fails but the step is already gone, so
the user sees nothing — and a re-tap is eaten as the answer to the NEXT question.

Fix: send the question first, commit only if it succeeds.
"""
import asyncio
from types import SimpleNamespace

import pytest

import app.services.survey_service as svc
from app.utils.survey_loader import Survey

SURVEY = Survey(**{
    "version": "atomic_test",
    "onstart": "r",
    "questions": {
        "q1": {"id": "q1", "type": "quick_reply", "text": "Q1?",
               "options": [{"label": "A", "action_type": "message", "value": "A"}]},
        "q2": {"id": "q2", "type": "quick_reply", "text": "Q2?",
               "options": [{"label": "B", "action_type": "message", "value": "B"}]},
    },
    "routes": {"r": {"questions": ["q1", "q2"], "next": None}},
})


def _wire(monkeypatch, send):
    """Fake session at q1 (step 0); patch repo + survey_manager + send_question."""
    session = SimpleNamespace(
        survey_version="atomic_test", current_route_id="r", current_step=0,
        route_history=[], payload={}, pending_multi_select={},
    )
    save = svc.repo.save_session  # placeholder, replaced below
    save_spy = _AsyncSpy()
    monkeypatch.setattr(svc.repo, "load_session", _const_async(session))
    monkeypatch.setattr(svc.repo, "save_session", save_spy)
    monkeypatch.setattr(svc.survey_manager, "get_survey", lambda v: SURVEY)
    monkeypatch.setattr(svc.survey_manager, "get_question",
                        lambda v, qid: SURVEY.questions[qid])
    monkeypatch.setattr(svc.messages, "send_question", send)
    return session, save_spy


class _AsyncSpy:
    def __init__(self): self.calls = 0
    async def __call__(self, *a, **k): self.calls += 1


def _const_async(value):
    async def f(*a, **k): return value
    return f


def test_step_not_advanced_when_reply_fails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("reply token expired")  # simulate poor connection
    session, save_spy = _wire(monkeypatch, boom)

    with pytest.raises(RuntimeError):
        asyncio.run(svc.process_survey_answer("U1", "A", "tok", None, None))

    assert session.current_step == 0, "step must NOT advance when the reply fails"
    assert save_spy.calls == 0, "must not commit when the reply fails"


def test_step_advances_when_reply_succeeds(monkeypatch):
    session, save_spy = _wire(monkeypatch, _AsyncSpy())

    asyncio.run(svc.process_survey_answer("U1", "A", "tok", None, None))

    assert session.current_step == 1, "step advances after a successful reply"
    assert save_spy.calls == 1, "commits exactly once on success"
