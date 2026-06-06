from app.services.survey_repository import build_location_point


def test_builds_point_from_location_answer():
    payload = {"q1": "hot", "q_loc": {"lat": 13.736, "lng": 100.523}}
    assert build_location_point(payload) == "SRID=4326;POINT(100.523 13.736)"


def test_none_when_no_location_answer():
    assert build_location_point({"q1": "hot", "q2": "noisy"}) is None


def test_picks_the_latlng_dict_among_other_dicts():
    payload = {
        "q_img": {"image_id": "abc", "image_url": "/x"},  # dict, but no lat/lng
        "q_loc": {"lat": 1.5, "lng": 2.5},
    }
    assert build_location_point(payload) == "SRID=4326;POINT(2.5 1.5)"
