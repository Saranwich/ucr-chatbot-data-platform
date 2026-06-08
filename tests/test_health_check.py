import asyncio

from app.main import health_check


def test_health_check_returns_ok():
    assert asyncio.run(health_check()) == {"status": "ok"}
