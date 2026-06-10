"""Resolve a trusted lineuser_id from a LIFF access token (ADR 0004).

The report form sends the user's LIFF access token in the Authorization header.
We verify it WITH LINE (the profile API) to obtain a trusted userId — never
trust a userId sent in the request body, it can be forged.

The form degrades to anonymous when opened outside LINE (dev / no LIFF id):
- no Authorization header  -> returns None (anonymous report)
- a header LINE rejects     -> raises 401 (a forged/expired token can't slip through)
"""
from typing import Optional

import aiohttp
from fastapi import HTTPException

LINE_PROFILE_URL = "https://api.line.me/v2/profile"


async def resolve_lineuser_id(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None  # anonymous — no LIFF token (dev / opened outside LINE)

    token = authorization.split(" ", 1)[1]
    async with aiohttp.ClientSession() as session:
        async with session.get(
            LINE_PROFILE_URL, headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=401, detail="LINE rejected the token")
            profile = await resp.json()
    return profile.get("userId")
