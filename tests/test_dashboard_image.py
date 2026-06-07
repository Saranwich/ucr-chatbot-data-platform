from app.routes.dashboard import extract_images


def test_no_images_returns_empty_list():
    payload = {"q1": "hot", "q_loc": {"lat": 1.5, "lng": 2.5}}
    assert extract_images(payload) == []


def test_single_image_is_extracted():
    payload = {
        "q_socratic_implication": "อากาศร้อนจัด",
        "q_photo": {"image_id": "617445", "image_url": "/api/dashboard/image/617445"},
    }
    assert extract_images(payload) == [
        {"question_id": "q_photo", "image_id": "617445", "image_url": "/api/dashboard/image/617445"},
    ]


def test_multiple_images_are_all_kept():
    # one record may carry more than one photo answer (e.g. front + back)
    payload = {
        "q_heat_photo": {"image_id": "111", "image_url": "/api/dashboard/image/111"},
        "q_text": "ร้อนมาก",
        "q_flood_photo": {"image_id": "222", "image_url": "/api/dashboard/image/222"},
    }
    images = extract_images(payload)
    assert len(images) == 2
    assert {img["image_id"] for img in images} == {"111", "222"}


def test_image_url_is_derived_when_missing():
    # if payload only stored image_id, build the proxy url from it
    payload = {"q_photo": {"image_id": "999"}}
    assert extract_images(payload) == [
        {"question_id": "q_photo", "image_id": "999", "image_url": "/api/dashboard/image/999"},
    ]


def test_location_dict_is_not_mistaken_for_an_image():
    payload = {"q_loc": {"lat": 1.5, "lng": 2.5}}
    assert extract_images(payload) == []


def test_non_dict_payload_is_safe():
    assert extract_images(None) == []
    assert extract_images("oops") == []
