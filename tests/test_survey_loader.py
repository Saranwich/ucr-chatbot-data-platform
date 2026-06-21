import json
import pytest
from pathlib import Path
from app.utils.survey_loader import SurveyManager

MINIMAL_SURVEY = {
    "version": "test_v1",
    "onstart": "main_route",
    "questions": {
        "q_topic": {
            "id": "q_topic",
            "type": "quick_reply",
            "text": "What to report?",
            "options": [
                {"label": "Heat", "action_type": "message", "value": "heat"},
                {"label": "Flood", "action_type": "message", "value": "flood"}
            ]
        },
        "q_location": {
            "id": "q_location",
            "type": "location",
            "text": "Where is the problem?",
            "options": [
                {"label": "Send location", "action_type": "location"}
            ]
        }
    },
    "routes": {
        "main_route": {"questions": ["q_topic", "q_location"], "next": None}
    }
}


@pytest.fixture
def survey_file(tmp_path):
    f = tmp_path / "test_v1.json"
    f.write_text(json.dumps(MINIMAL_SURVEY))
    return f


@pytest.fixture
def manager(survey_file):
    m = SurveyManager()
    m.load_from_file(str(survey_file))
    return m


# --- Behavior 1: valid JSON loads and get_question returns the right question ---

def test_get_question_returns_correct_question(manager):
    question = manager.get_question("test_v1", "q_topic")
    assert question is not None
    assert question.id == "q_topic"
    assert question.text == "What to report?"
    assert len(question.options) == 2


# --- Behavior 2: malformed JSON raises at load time ---

def test_malformed_json_raises_on_load(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": "bad_v1"}))  # missing onstart/questions/routes
    m = SurveyManager()
    with pytest.raises(Exception):
        m.load_from_file(str(bad))


# --- Behavior 3: unknown question ID returns None ---

def test_get_question_returns_none_for_unknown_id(manager):
    assert manager.get_question("test_v1", "does_not_exist") is None


# --- Behavior 4: get_route returns the Route with questions in correct order ---

def test_get_route_returns_ordered_question_ids(manager):
    route = manager.get_route("test_v1", "main_route")
    assert route.questions == ["q_topic", "q_location"]
    assert route.next is None


# --- Behavior 5: an orchestrator in a route's `next` is correctly parsed ---

def test_route_next_parses_orchestrator(tmp_path):
    survey_with_orchestrator = {
        "version": "orch_v1",
        "onstart": "main_route",
        "questions": {
            "q_topic": {"id": "q_topic", "type": "quick_reply", "text": "Topic?",
                        "options": [{"label": "Heat", "action_type": "message", "value": "heat"}]},
        },
        "routes": {
            "main_route": {
                "questions": ["q_topic"],
                "next": {
                    "conditions": [{"when": {"q_topic": "heat"}, "goto": "heat_route"}],
                    "default": None,
                },
            },
            "heat_route": {"questions": [], "next": None},
        },
    }
    f = tmp_path / "orch_v1.json"
    f.write_text(json.dumps(survey_with_orchestrator))
    m = SurveyManager()
    m.load_from_file(str(f))

    orchestrator = m.get_route("orch_v1", "main_route").next
    condition = orchestrator.conditions[0]
    assert condition.when == {"q_topic": "heat"}
    assert condition.goto == "heat_route"
    assert orchestrator.default is None


# --- Behavior 6: two versions loaded independently ---

def test_two_versions_do_not_bleed(tmp_path):
    v2 = {
        "version": "test_v2",
        "onstart": "route_a",
        "questions": {
            "q_only_in_v2": {"id": "q_only_in_v2", "type": "quick_reply", "text": "V2 only",
                              "options": []}
        },
        "routes": {"route_a": {"questions": ["q_only_in_v2"], "next": None}}
    }
    v2_file = tmp_path / "test_v2.json"
    v2_file.write_text(json.dumps(v2))

    v1_file = tmp_path / "test_v1.json"
    v1_file.write_text(json.dumps(MINIMAL_SURVEY))

    m = SurveyManager()
    m.load_from_file(str(v1_file))
    m.load_from_file(str(v2_file))

    assert m.get_question("test_v1", "q_only_in_v2") is None
    assert m.get_question("test_v2", "q_only_in_v2") is not None
    assert m.get_question("test_v2", "q_topic") is None
