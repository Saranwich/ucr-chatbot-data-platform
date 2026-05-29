import json
import pytest
from pathlib import Path
from app.utils.survey_loader import SurveyManager

MINIMAL_SURVEY = {
    "version": "test_v1",
    "questions": {
        "q_topic": {
            "id": "q_topic",
            "type": "quick_reply",
            "text": "What to report?",
            "options": [
                {"label": "Heat", "action_type": "message", "value": "heat", "next_question_id": "q_location"},
                {"label": "Flood", "action_type": "message", "value": "flood", "next_question_id": "q_location"}
            ]
        },
        "q_location": {
            "id": "q_location",
            "type": "location",
            "text": "Where is the problem?",
            "options": [
                {"label": "Send location", "action_type": "location", "next_question_id": None}
            ]
        }
    },
    "routes": {
        "main_route": ["q_topic", "q_location"]
    },
    "flow": {
        "onstart": "main_route",
        "after": {"main_route": None},
        "forks": {}
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
    bad.write_text(json.dumps({"version": "bad_v1"}))  # missing questions/routes/flow
    m = SurveyManager()
    with pytest.raises(Exception):
        m.load_from_file(str(bad))


# --- Behavior 3: unknown question ID returns None ---

def test_get_question_returns_none_for_unknown_id(manager):
    assert manager.get_question("test_v1", "does_not_exist") is None


# --- Behavior 4: get_route returns questions in correct order ---

def test_get_route_returns_ordered_question_ids(manager):
    route = manager.get_route("test_v1", "main_route")
    assert route == ["q_topic", "q_location"]


# --- Behavior 5: dispatcher in flow is correctly parsed ---

def test_get_flow_parses_dispatcher(tmp_path):
    survey_with_dispatcher = {
        "version": "dispatch_v1",
        "questions": {
            "q_topic": {"id": "q_topic", "type": "quick_reply", "text": "Topic?",
                        "options": [{"label": "Heat", "action_type": "message", "value": "heat", "next_question_id": None}]},
        },
        "routes": {
            "main_route": ["q_topic"],
            "heat_route": []
        },
        "flow": {
            "onstart": "main_route",
            "after": {
                "main_route": {
                    "type": "dispatcher",
                    "look_up_answer_of": "q_topic",
                    "map": {"heat": "heat_route"}
                },
                "heat_route": None
            },
            "forks": {}
        }
    }
    f = tmp_path / "dispatch_v1.json"
    f.write_text(json.dumps(survey_with_dispatcher))
    m = SurveyManager()
    m.load_from_file(str(f))

    flow = m.get_flow("dispatch_v1")
    dispatcher = flow.after["main_route"]
    assert dispatcher.type == "dispatcher"
    assert dispatcher.look_up_answer_of == "q_topic"
    assert dispatcher.map["heat"] == "heat_route"


# --- Behavior 6: two versions loaded independently ---

def test_two_versions_do_not_bleed(tmp_path):
    v2 = {
        "version": "test_v2",
        "questions": {
            "q_only_in_v2": {"id": "q_only_in_v2", "type": "quick_reply", "text": "V2 only",
                              "options": []}
        },
        "routes": {"route_a": ["q_only_in_v2"]},
        "flow": {"onstart": "route_a", "after": {"route_a": None}, "forks": {}}
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
