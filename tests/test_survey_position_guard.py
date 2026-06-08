"""Guard for a survey file that changed while a user was mid-session.

`session_position_is_valid` is a pure check used by process_survey_answer to
decide whether the session's saved (route, step) still resolves against the
current survey definition. If it doesn't, the caller clears the stale session
and asks the user to restart instead of crashing (500).
"""
from app.utils.survey_loader import Survey, Route
from app.services.survey_service import session_position_is_valid


def _survey():
    """A minimal one-route survey with two questions."""
    return Survey(
        version="v1",
        onstart="main",
        questions={},  # not consulted by the position guard
        routes={"main": Route(questions=["q1", "q2"])},
    )


def test_valid_position_passes():
    survey = _survey()
    assert session_position_is_valid(survey, "main", 0) is True
    assert session_position_is_valid(survey, "main", 1) is True


def test_missing_survey_version_is_invalid():
    # version deleted -> get_survey returns None
    assert session_position_is_valid(None, "main", 0) is False


def test_missing_route_is_invalid():
    # the route the session sat in no longer exists in the file
    assert session_position_is_valid(_survey(), "gone", 0) is False


def test_step_out_of_range_is_invalid():
    # survey was shortened: route now has 2 questions, session is at step 5
    assert session_position_is_valid(_survey(), "main", 5) is False


def test_step_equal_to_length_is_invalid():
    # boundary: index == len is out of range (valid indices are 0..len-1)
    assert session_position_is_valid(_survey(), "main", 2) is False


def test_negative_step_is_invalid():
    assert session_position_is_valid(_survey(), "main", -1) is False
