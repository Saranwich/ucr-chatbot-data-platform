from datetime import date

import pytest
from fastapi import HTTPException

from app.services.dashboard import parse_date_filter


def test_none_means_no_filter():
    assert parse_date_filter(None) is None


def test_empty_string_means_no_filter():
    assert parse_date_filter("") is None


def test_valid_date_is_parsed():
    assert parse_date_filter("2026-06-08") == date(2026, 6, 8)


def test_malformed_date_raises_400():
    with pytest.raises(HTTPException) as exc:
        parse_date_filter("not-a-date")
    assert exc.value.status_code == 400


def test_wrong_shape_date_raises_400():
    # right idea, wrong format (DD-MM-YYYY) — must not silently pass through
    with pytest.raises(HTTPException) as exc:
        parse_date_filter("08-06-2026")
    assert exc.value.status_code == 400
