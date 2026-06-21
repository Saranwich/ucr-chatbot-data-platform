import asyncio
import json

from app.main import global_exception_handler


def test_500_response_hides_internal_detail():
    resp = asyncio.run(global_exception_handler(None, Exception("boom secret detail")))
    assert resp.status_code == 500

    body = json.loads(resp.body)
    assert body == {"detail": "Internal Server Error"}

    # the traceback and the exception message must never reach the caller
    leaked = resp.body.decode().lower()
    assert "traceback" not in leaked
    assert "boom" not in leaked
