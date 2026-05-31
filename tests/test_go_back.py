import pytest
from app.utils.survey_loader import Survey
from app.services.routing import compute_go_back_state

SURVEY_DATA = {
    "version": "goback_test",
    "onstart": "start_route",
    "questions": {
        "q1": {"id": "q1", "type": "quick_reply", "text": "Q1?",
               "options": [{"label": "A", "action_type": "message", "value": "heat"}]},
        "q2": {"id": "q2", "type": "quick_reply", "text": "Q2?",
               "options": [{"label": "B", "action_type": "message", "value": "B"}]},
        "q_heat": {"id": "q_heat", "type": "quick_reply", "text": "Heat Q?",
                   "options": [{"label": "C", "action_type": "message", "value": "C"}]},
    },
    "routes": {
        "start_route": {
            "questions": ["q1", "q2"],
            "next": {
                "conditions": [{"when": {"q1": "heat"}, "goto": "heat_route"}],
                "default": None,
            },
        },
        "heat_route": {"questions": ["q_heat"], "next": None},
    },
}


@pytest.fixture
def survey():
    return Survey(**SURVEY_DATA)


# --- Behavior 1: within-route go-back decrements step ---

def test_within_route_go_back_returns_previous_step(survey):
    result = compute_go_back_state("start_route", 1, [], survey)
    assert result["action"] == "within_route"
    assert result["route_id"] == "start_route"
    assert result["step"] == 0
    assert result["question_id"] == "q1"


# --- Behavior 2: cross-route go-back pops history stack ---

def test_cross_route_go_back_pops_history(survey):
    history = [{"route_id": "start_route", "step": 1}]
    result = compute_go_back_state("heat_route", 0, history, survey)
    assert result["action"] == "cross_route"
    assert result["route_id"] == "start_route"
    assert result["step"] == 1
    assert result["question_id"] == "q2"
    assert result["route_history"] == []


# --- Behavior 3: at beginning — nothing to go back to ---

def test_at_beginning_returns_at_beginning(survey):
    result = compute_go_back_state("start_route", 0, [], survey)
    assert result["action"] == "at_beginning"


# --- Behavior 4: cross-route preserves deeper history ---

def test_cross_route_preserves_older_history(survey):
    history = [
        {"route_id": "start_route", "step": 0},
        {"route_id": "start_route", "step": 1},
    ]
    result = compute_go_back_state("heat_route", 0, history, survey)
    assert result["route_history"] == [{"route_id": "start_route", "step": 0}]
