import asyncio

import pytest
from fastapi import HTTPException

from app.routes.dashboard import fetch_image_content


class _FakeBlob:
    """Stand-in for AsyncMessagingApiBlob — no network."""

    def __init__(self, *, returns=None, raises=None):
        self._returns = returns
        self._raises = raises

    async def get_message_content(self, image_id):
        if self._raises is not None:
            raise self._raises
        return self._returns


def test_valid_image_returns_bytes():
    blob = _FakeBlob(returns=b"jpeg-bytes")
    assert asyncio.run(fetch_image_content(blob, "123")) == b"jpeg-bytes"


def test_expired_image_raises_404():
    # LINE has deleted the image — the CDN call throws
    blob = _FakeBlob(raises=Exception("content not found"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(fetch_image_content(blob, "gone"))
    assert exc.value.status_code == 404
