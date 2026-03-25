"""Kling API JWT authentication helper.

Kling requires a signed JWT using KLING_API_KEY (iss) and KLING_API_SECRET (signing key).
See: https://docs.klingai.com/api-reference/authentication
"""
from __future__ import annotations

import time
import hmac
import hashlib
import base64
import json


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_kling_jwt(api_key: str, api_secret: str, expire_seconds: int = 1800) -> str:
    """Build a signed HS256 JWT for Kling API authentication.

    Args:
        api_key: KLING_API_KEY — used as the JWT `iss` claim.
        api_secret: KLING_API_SECRET — used as the HMAC-SHA256 signing key.
        expire_seconds: Token lifetime in seconds (default 30 min).

    Returns:
        Signed JWT string suitable for use as a Bearer token.
    """
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps(
            {"iss": api_key, "exp": now + expire_seconds, "nbf": now - 5},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = _b64url(
        hmac.new(
            api_secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
    )
    return f"{signing_input}.{signature}"
