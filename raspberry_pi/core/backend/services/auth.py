"""JWT authentication, role checks and group scoping for the API.

Environment variables:
  JWT_SECRET          signing secret (32+ characters). A random one is used if missing,
                      which invalidates every token at each restart.
  JWT_EXPIRE_MINUTES  token lifetime (default 60).
  AUTH_REQUIRED       "false" turns protection off. Local development ONLY.
"""

import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

try:
    import jwt
except ImportError:
    import base64
    import hashlib
    import hmac
    import json

    class _FallbackJWT:
        """Lightweight HS256 JWT fallback when PyJWT is not installed."""
        class PyJWTError(Exception):
            pass

        @staticmethod
        def _b64e(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

        @staticmethod
        def _b64d(s: str) -> bytes:
            s += "=" * ((4 - len(s) % 4) % 4)
            return base64.urlsafe_b64decode(s.encode("ascii"))

        @classmethod
        def encode(cls, payload: dict, key: str, algorithm: str = "HS256") -> str:
            header = {"alg": "HS256", "typ": "JWT"}
            h_str = cls._b64e(json.dumps(header, separators=(",", ":")).encode("utf-8"))
            p = {}
            for k, v in payload.items():
                if hasattr(v, "timestamp"):
                    p[k] = int(v.timestamp())
                else:
                    p[k] = v
            p_str = cls._b64e(json.dumps(p, separators=(",", ":")).encode("utf-8"))
            sig = hmac.new(key.encode("utf-8"), f"{h_str}.{p_str}".encode("utf-8"), hashlib.sha256).digest()
            return f"{h_str}.{p_str}.{cls._b64e(sig)}"

        @classmethod
        def decode(cls, token: str, key: str, algorithms: list = None) -> dict:
            parts = token.split(".")
            if len(parts) != 3:
                raise cls.PyJWTError("Invalid token format")
            h_str, p_str, sig_str = parts
            expected = hmac.new(key.encode("utf-8"), f"{h_str}.{p_str}".encode("utf-8"), hashlib.sha256).digest()
            if not hmac.compare_digest(cls._b64d(sig_str), expected):
                raise cls.PyJWTError("Signature verification failed")
            claims = json.loads(cls._b64d(p_str).decode("utf-8"))
            if "exp" in claims and claims["exp"] < time.time():
                raise cls.PyJWTError("Token has expired")
            return claims

    jwt = _FallbackJWT

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services import user_store

logger = logging.getLogger("auth")

ALGORITHM = "HS256"
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").strip().lower() != "false"
MAX_FAILURES, WINDOW_S = 5, 300

_secret = os.getenv("JWT_SECRET", "")
if len(_secret) < 32:
    _secret = secrets.token_urlsafe(48)
    logger.warning("JWT_SECRET missing or shorter than 32 characters: using a random secret "
                   "(tokens are invalidated at every restart). Set JWT_SECRET in .env.")
if not AUTH_REQUIRED:
    logger.warning("AUTH_REQUIRED=false: the API is NOT protected. Never use this outside local development.")

_bearer = HTTPBearer(auto_error=False)
_failures: dict = {}


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["id"]), "email": user["email"], "role": user["role"],
              "group_code": user["group_code"], "iat": now, "exp": now + timedelta(minutes=EXPIRE_MINUTES)}
    return jwt.encode(claims, _secret, algorithm=ALGORITHM)


def _denied() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def get_authenticated_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Valid token required. The user is re-read from the database on every request,
    so a deactivation or a role change takes effect immediately."""
    if not AUTH_REQUIRED:
        return {"id": None, "first_name": "Local", "last_name": "dev", "email": "dev@local",
                "role": "admin", "group_code": None, "active": True}
    if creds is None:
        raise _denied()
    try:
        claims = jwt.decode(creds.credentials, _secret, algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise _denied()
    user = user_store.get_user(claims["sub"])
    if not user or not user["active"]:
        raise _denied()
    return user


def get_current_user(user: dict = Depends(get_authenticated_user)) -> dict:
    """Regular API access requires the initial password to be changed."""
    if user.get("password_change_required"):
        raise HTTPException(status_code=403, detail="Password change required")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def scope_group(user: dict):
    """Group a query must be limited to: None for admins (no limit). A technician
    without a group matches nothing."""
    return None if user["role"] == "admin" else (user["group_code"] or "-")


# --- login throttling (in memory, per e-mail) ---------------------------------
def check_throttle(key: str) -> None:
    now = time.time()
    if len(_failures) > 5000:
        _failures.clear()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW_S]
    _failures[key] = recent
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many failed attempts, try again in a few minutes")


def record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.time())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
