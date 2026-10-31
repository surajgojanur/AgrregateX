"""Demo authentication: fixed demo users, HMAC-signed HttpOnly session cookie.

Users: tenant<N>@demo.local -> tenant N (sees only tenant N), admin@demo.local -> operator
(may select any tenant and read engine internals). One shared demo password from
AX_DEMO_PASSWORD. This is a hackathon demo login, not production identity management.
"""
import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import config

COOKIE = "ax_session"
_TENANT_RE = re.compile(r"^tenant(\d{1,4})@demo\.local$")


@dataclass(frozen=True)
class User:
    email: str
    role: str  # "tenant" | "admin"
    tenant_id: int | None

    def public(self) -> dict:
        name = "Operator (all tenants)" if self.role == "admin" else f"Tenant {self.tenant_id}"
        return {"id": self.email, "name": name, "email": self.email, "role": self.role,
                "tenant_id": self.tenant_id}

    def can_read_tenant(self, tenant_id: int) -> bool:
        return self.role == "admin" or self.tenant_id == tenant_id


def lookup(email: str) -> User | None:
    email = email.strip().lower()
    if email == "admin@demo.local":
        return User(email, "admin", None)
    m = _TENANT_RE.match(email)
    if m and 1 <= int(m.group(1)) <= config.DEMO_TENANTS:
        return User(email, "tenant", int(m.group(1)))
    return None


def check_password(password: str) -> bool:
    if not config.DEMO_PASSWORD:
        return False  # login disabled until the deployment sets a demo password
    return hmac.compare_digest(password.encode(), config.DEMO_PASSWORD.encode())


def _sign(payload: bytes) -> str:
    mac = hmac.new(config.SESSION_SECRET, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def issue(user: User) -> str:
    body = json.dumps({"e": user.email, "x": int(time.time()) + config.SESSION_TTL_S}).encode()
    b = base64.urlsafe_b64encode(body).decode().rstrip("=")
    return f"{b}.{_sign(body)}"


def verify(token: str | None) -> User | None:
    if not token or "." not in token:
        return None
    b, sig = token.rsplit(".", 1)
    try:
        body = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if int(data.get("x", 0)) < time.time():
        return None
    return lookup(str(data.get("e", "")))


def current_user(request: Request) -> User:
    if config.AUTH_DISABLED:
        return User("admin@demo.local", "admin", None)
    user = verify(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Not signed in.")
    return user


def require_admin(request: Request) -> User:
    user = current_user(request)
    if user.role != "admin":
        raise HTTPException(403, "Operator access required.")
    return user


def authorize_tenant(user: User, tenant_id: int) -> int:
    # Same answer for "not yours" and "does not exist": no tenant enumeration.
    if not user.can_read_tenant(tenant_id):
        raise HTTPException(403, "You do not have access to this tenant.")
    return tenant_id
