import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response, status

from app.database import get_connection


ADMIN_COOKIE_NAME = "maison_muse_admin"
ADMIN_WS_COOKIE_NAME = "maison_muse_admin_ws"
SESSION_SECONDS = 8 * 60 * 60
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_MINUTES = 15
VALID_ADMIN_ROLES = {
    "Super Admin",
    "Store Manager",
    "Support Agent",
    "Inventory Clerk",
}


def _configured(name: str) -> str:
    return os.getenv(name, "").strip()


def _session_secret() -> bytes:
    secret = _configured("ADMIN_SESSION_SECRET")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured. Set ADMIN_SESSION_SECRET.",
        )
    return secret.encode("utf-8")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _session_payload(token: str) -> dict[str, Any] | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _session_secret(), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        supplied_signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None
        payload = json.loads(
            base64.urlsafe_b64decode(
                encoded_payload + "=" * (-len(encoded_payload) % 4)
            )
        )
        if (
            not isinstance(payload.get("sub"), str)
            or not isinstance(payload.get("sid"), str)
            or payload.get("role") not in VALID_ADMIN_ROLES
            or payload.get("exp", 0) <= time.time()
        ):
            return None
        return payload
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return None


def _encode_session(username: str, role: str, session_id: str) -> str:
    payload = json.dumps(
        {
            "sub": username,
            "role": role,
            "sid": session_id,
            "exp": int(time.time()) + SESSION_SECONDS,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(
        _session_secret(), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def _audit_auth_event(
    username: str,
    ip_address: str,
    event_type: str,
    description: str,
    severity: str,
    user_agent: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_audit_logs (
                occurred_at, admin_username, event_category, event_type,
                description, ip_address, severity, details_json
            ) VALUES (?, ?, 'Auth', ?, ?, ?, ?, ?)
            """,
            (
                now,
                username,
                event_type,
                description,
                ip_address,
                severity,
                json.dumps({"user_agent": user_agent[:500]}),
            ),
        )
        connection.commit()


def current_admin_details(request: Request) -> dict[str, str] | None:
    session_cookie = request.cookies.get(ADMIN_COOKIE_NAME, "") or request.cookies.get(
        ADMIN_WS_COOKIE_NAME, ""
    )
    payload = _session_payload(session_cookie)
    if not payload:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        session = connection.execute(
            """
            SELECT role, revoked_at FROM admin_sessions
            WHERE session_id = ? AND username = ?
            """,
            (payload["sid"], payload["sub"]),
        ).fetchone()
        if session is None or session["revoked_at"] is not None:
            return None
        connection.execute(
            "UPDATE admin_sessions SET last_active_at = ? WHERE session_id = ?",
            (now, payload["sid"]),
        )
        connection.commit()
    return {
        "username": payload["sub"],
        "role": session["role"],
        "session_id": payload["sid"],
    }


def current_admin(request: Request) -> str | None:
    details = current_admin_details(request)
    return details["username"] if details else None


def require_admin(request: Request) -> str:
    details = current_admin_details(request)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin sign-in is required.",
        )
    request.state.admin_identity = details
    return details["username"]


def login_admin(username: str, password: str, request: Request, response: Response) -> dict:
    configured_username = _configured("ADMIN_USERNAME")
    configured_password = _configured("ADMIN_PASSWORD")
    if not configured_username or not configured_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent", "unknown")[:500]
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)).isoformat()
    with get_connection() as connection:
        attempts = connection.execute(
            """
            SELECT COUNT(*) FROM admin_login_attempts
            WHERE ip_address = ? AND succeeded = 0 AND created_at >= ?
            """,
            (ip_address, cutoff),
        ).fetchone()[0]
        if attempts >= LOGIN_FAILURE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed sign-in attempts. Try again in 15 minutes.",
            )

    username_matches = hmac.compare_digest(
        username.encode(), configured_username.encode()
    )
    password_matches = hmac.compare_digest(
        password.encode(), configured_password.encode()
    )
    if not username_matches or not password_matches:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO admin_login_attempts (
                    username, ip_address, succeeded, created_at
                ) VALUES (?, ?, 0, ?)
                """,
                (username[:80], ip_address, now.isoformat()),
            )
            connection.commit()
        _audit_auth_event(
            username[:80] or "Unknown",
            ip_address,
            "LOGIN_FAILED",
            "Failed administrator sign-in attempt.",
            "WARNING" if attempts < 2 else "CRITICAL",
            user_agent,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The username or password is incorrect.",
        )

    configured_role = _configured("ADMIN_ROLE") or "Super Admin"
    if configured_role not in VALID_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_ROLE must be a supported admin role.",
        )
    session_id = uuid.uuid4().hex
    session = _encode_session(configured_username, configured_role, session_id)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_login_attempts (
                username, ip_address, succeeded, created_at
            ) VALUES (?, ?, 1, ?)
            """,
            (configured_username, ip_address, now.isoformat()),
        )
        connection.execute(
            """
            INSERT INTO admin_sessions (
                session_id, username, role, ip_address, user_agent,
                created_at, last_active_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                configured_username,
                configured_role,
                ip_address,
                user_agent,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO admin_audit_logs (
                occurred_at, admin_username, event_category, event_type,
                description, ip_address, severity, details_json
            ) VALUES (?, ?, 'Auth', 'LOGIN_SUCCESS', 'Administrator signed in.',
                      ?, 'INFO', ?)
            """,
            (
                now.isoformat(),
                configured_username,
                ip_address,
                json.dumps({"session_id": session_id, "user_agent": user_agent}),
            ),
        )
        connection.commit()
    secure_cookie = os.getenv("ADMIN_COOKIE_SECURE", "false").strip().casefold() == "true"
    response.set_cookie(
        ADMIN_COOKIE_NAME,
        session,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/api/admin",
    )
    response.set_cookie(
        ADMIN_WS_COOKIE_NAME,
        session,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/ws/support",
    )
    return {
        "username": configured_username,
        "role": configured_role,
        "session_id": session_id,
    }


def logout_admin(request: Request, response: Response) -> dict[str, str]:
    details = current_admin_details(request)
    if details:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            connection.execute(
                "UPDATE admin_sessions SET revoked_at = ? WHERE session_id = ?",
                (now, details["session_id"]),
            )
            connection.execute(
                """
                INSERT INTO admin_audit_logs (
                    occurred_at, admin_username, event_category, event_type,
                    description, ip_address, severity, details_json
                ) VALUES (?, ?, 'Auth', 'LOGOUT', 'Administrator signed out.',
                          ?, 'INFO', ?)
                """,
                (
                    now,
                    details["username"],
                    _client_ip(request),
                    json.dumps({"session_id": details["session_id"]}),
                ),
            )
            connection.commit()
    response.delete_cookie(
        ADMIN_COOKIE_NAME,
        httponly=True,
        secure=os.getenv("ADMIN_COOKIE_SECURE", "false").strip().casefold() == "true",
        samesite="strict",
        path="/api/admin",
    )
    response.delete_cookie(
        ADMIN_WS_COOKIE_NAME,
        httponly=True,
        secure=os.getenv("ADMIN_COOKIE_SECURE", "false").strip().casefold() == "true",
        samesite="strict",
        path="/ws/support",
    )
    return {"message": "Admin session ended."}
