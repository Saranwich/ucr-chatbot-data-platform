import asyncio

from app.routes.report import point_wkt, unique_image_name
from app.utils.liff_auth import resolve_lineuser_id


# --- point_wkt -------------------------------------------------------------

def test_point_wkt_builds_postgis_point():
    assert point_wkt(13.736, 100.523) == "SRID=4326;POINT(100.523 13.736)"


def test_point_wkt_none_when_either_coord_missing():
    assert point_wkt(None, 100.5) is None
    assert point_wkt(13.7, None) is None
    assert point_wkt(None, None) is None


# --- unique_image_name -----------------------------------------------------

def test_unique_image_name_keeps_extension():
    assert unique_image_name("IMG_0001.png").endswith(".png")


def test_unique_image_name_defaults_to_jpg_without_extension():
    assert unique_image_name("photo").endswith(".jpg")
    assert unique_image_name("").endswith(".jpg")
    assert unique_image_name(None).endswith(".jpg")


def test_unique_image_name_is_unique_per_call():
    # same original name -> different stored names (no collision)
    a = unique_image_name("IMG_0001.jpg")
    b = unique_image_name("IMG_0001.jpg")
    assert a != b
    # stem is a 32-char uuid hex
    assert len(a.split(".")[0]) == 32


# --- resolve_lineuser_id (anonymous branch — no network) -------------------

def test_resolve_lineuser_id_anonymous_without_bearer_token():
    # missing / non-bearer header -> anonymous (None), never hits LINE
    assert asyncio.run(resolve_lineuser_id(None)) is None
    assert asyncio.run(resolve_lineuser_id("")) is None
    assert asyncio.run(resolve_lineuser_id("Basic abc")) is None
    assert asyncio.run(resolve_lineuser_id("token-without-bearer")) is None
