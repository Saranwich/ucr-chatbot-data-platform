from types import SimpleNamespace

from app.services.survey_repository import build_incomplete_report
from app.utils.survey_loader import SurveyManager
from app.routes.dashboard import resolve_drop_off_question


def test_build_incomplete_report_preserves_session_progress():
    session = SimpleNamespace(
        lineuser_id="U123",
        survey_version="community_report_v1",
        current_route_id="environment",
        current_step=2,
        payload={
            "q_problem": "heat",
            "q_location": {"lat": 13.736, "lng": 100.523},
        },
    )

    report = build_incomplete_report(session, status="restarted")

    assert report.lineuser_id == "U123"
    assert report.survey_version == "community_report_v1"
    assert report.drop_off_route_id == "environment"
    assert report.drop_off_step == 2
    assert report.payload == session.payload
    assert report.location_data == "SRID=4326;POINT(100.523 13.736)"
    assert report.status == "restarted"


def test_resolve_drop_off_question_returns_question_at_saved_position(tmp_path):
    survey_file = tmp_path / "survey.json"
    survey_file.write_text(
        """
        {
          "version": "test_v1",
          "onstart": "main",
          "questions": {
            "q_topic": {"id": "q_topic", "type": "quick_reply", "text": "Topic?", "options": []},
            "q_location": {"id": "q_location", "type": "location", "text": "Where?", "options": []}
          },
          "routes": {"main": {"questions": ["q_topic", "q_location"], "next": null}}
        }
        """
    )
    manager = SurveyManager()
    manager.load_from_file(str(survey_file))

    question_id, question_text = resolve_drop_off_question(
        manager, "test_v1", "main", 1
    )

    assert question_id == "q_location"
    assert question_text == "Where?"


def test_resolve_drop_off_question_handles_changed_survey_definition():
    manager = SurveyManager()

    assert resolve_drop_off_question(manager, "missing", "route", 3) == (None, None)
