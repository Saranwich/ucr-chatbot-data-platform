import base64
import hashlib
import hmac

from fastapi import Request

from app.core.config import LINE_CHANNEL_SECRET


async def verify_line_signature(req: Request) -> bool:
    """verify request is from line or not

    Args:
        req (Request): request from router

    Returns:
        bool: True if it's from line, otherwise False
    """
    body = await req.body()
    signature = req.headers.get("x-line-signature", "")

    expected = base64.b64encode(
        hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    )

    return hmac.compare_digest(expected, signature.encode())
