import pytest
from app.utils.survey_loader import Survey, SurveyQuestion, SurveyOption, SurveyFlow, Dispatcher
from app.services.routing import compute_next_state

# Shared fixture survey used across all tests:
# start_route: [q1, q2] → dispatcher → heat_route or flood_route → complete
SURVEY_DATA = {
    "version": "routing_test",
    "questions": {
        "q1": {"id": "q1", "type": "quick_reply", "text": "Q1?",
               "options": [{"label": "A", "action_type": "message", "value": "heat", "next_question_id": None}]},
        "q2": {"id": "q2", "type": "quick_reply", "text": "Q2?",
               "options": [{"label": "B", "action_type": "message", "value": "B", "next_question_id": None}]},
        "q_heat": {"id": "q_heat", "type": "quick_reply", "text": "Heat Q?",
                   "options": [{"label": "C", "action_type": "message", "value": "C", "next_question_id": None}]},
        "q_flood": {"id": "q_flood", "type": "quick_reply", "text": "Flood Q?",
                    "options": [{"label": "D", "action_type": "message", "value": "D", "next_question_id": None}]},
    },
    "routes": {
        "start_route": ["q1", "q2"],
        "heat_route":  ["q_heat"],
        "flood_route": ["q_flood"],
    },
    "flow": {
        "onstart": "start_route",
        "after": {
            "start_route": {
                "type": "dispatcher",
                "look_up_answer_of": "q1",
                "map": {"heat": "heat_route", "flood": "flood_route"},
                "default": None
            },
            "heat_route":  None,
            "flood_route": None,
        },
        "forks": {}
    }
}


@pytest.fixture
def survey():
    return Survey(**SURVEY_DATA)


# --- Behavior 1: mid-route answer → same route, step advances ---

def test_mid_route_answer_advances_step(survey):
    result = compute_next_state(
        current_route_id="start_route",
        current_step=0,
        route_history=[],
        payload={"q1": "heat"},
        survey=survey,
    )
    assert result["action"] == "next_question"
    assert result["current_route_id"] == "start_route"
    assert result["current_step"] == 1
    assert result["next_question_id"] == "q2"


# --- Behavior 2: last question of route with fixed next → moves to that route ---

def test_last_question_fixed_next_moves_to_next_route():
    fixed_survey = Survey(**{
        **SURVEY_DATA,
        "flow": {
            "onstart": "start_route",
            "after": {
                "start_route": "heat_route",
                "heat_route": None,
                "flood_route": None,
            },
            "forks": {}
        }
    })
    result = compute_next_state(
        current_route_id="start_route",
        current_step=1,  # last step of start_route (has 2 questions: index 0 and 1)
        route_history=[],
        payload={"q1": "heat", "q2": "B"},
        survey=fixed_survey,
    )
    assert result["action"] == "next_route"
    assert result["current_route_id"] == "heat_route"
    assert result["current_step"] == 0
    assert result["next_question_id"] == "q_heat"
    assert {"route_id": "start_route", "step": 1} in result["route_history"]


# --- Behavior 3: last question of route with dispatcher → picks route from payload ---

def test_last_question_dispatcher_picks_correct_route(survey):
    result = compute_next_state(
        current_route_id="start_route",
        current_step=1,  # last step of start_route
        route_history=[],
        payload={"q1": "flood", "q2": "B"},
        survey=survey,
    )
    assert result["action"] == "next_route"
    assert result["current_route_id"] == "flood_route"
    assert result["next_question_id"] == "q_flood"


# --- Behavior 4: last question of last route (next=null) → complete ---

def test_last_question_of_last_route_completes_survey(survey):
    result = compute_next_state(
        current_route_id="heat_route",
        current_step=0,  # only question in heat_route
        route_history=[{"route_id": "start_route", "step": 1}],
        payload={"q1": "heat", "q2": "B", "q_heat": "C"},
        survey=survey,
    )
    assert result["action"] == "complete"
    assert result["next_question_id"] is None


# --- Behavior 5: dispatcher with unrecognised answer falls back to default ---

def test_dispatcher_unknown_answer_uses_default(survey):
    result = compute_next_state(
        current_route_id="start_route",
        current_step=1,
        route_history=[],
        payload={"q1": "UNKNOWN_ANSWER", "q2": "B"},
        survey=survey,
    )
    # default is None → complete
    assert result["action"] == "complete"
    assert result["next_question_id"] is None
