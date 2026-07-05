import asyncio

from app.routes.system import health_check


class FakeDb:
    def __init__(self, fail=False):
        self.fail = fail

    async def execute(self, stmt):
        if self.fail:
            raise RuntimeError("db down")
        return None


def test_health_ok_when_db_reachable():
    assert asyncio.run(health_check(FakeDb())) == {"status": "ok", "database": "ok"}


def test_health_503_when_db_unreachable():
    # #75: a failed DB must surface as unhealthy, not a green "ok"
    resp = asyncio.run(health_check(FakeDb(fail=True)))
    assert resp.status_code == 503
