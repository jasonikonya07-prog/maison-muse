import re
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, status

from app.auth_security import (
    JWT_LIFETIME_SECONDS,
    create_access_token,
    decode_access_token,
    ensure_jwt_configured,
    password_hash,
    password_matches,
)
from app.config import auto_approve_seller_registrations_enabled
from app.database import get_connection
from app.seller_portal import ensure_seller_portal_open
from app.schemas import AuthLogin, AuthRegistration, GoogleAuthInput


router = APIRouter()
SELLER_PLAN_COMMISSION_RATES = {
    "boutique": 10.0,
    "pro": 5.0,
    "enterprise": 2.5,
}


def _safe_user(row: sqlite3.Row, seller: sqlite3.Row | None = None) -> dict:
    user = {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "phone": row["phone"],
        "business_type": row["business_type"],
        "whatsapp_number": row["whatsapp_number"],
    }
    if seller:
        user["seller"] = {
            "id": seller["id"],
            "store_name": seller["store_name"],
            "store_slug": seller["store_slug"],
            "business_type": seller["business_type"],
            "whatsapp_number": seller["whatsapp_number"],
            "status": seller["status"],
            "accepted_terms": bool(seller["accepted_terms"]),
            "selected_plan": seller["selected_plan"],
            "commission_rate": seller["commission_rate"],
        }
    return user


def _auth_response(row: sqlite3.Row, seller: sqlite3.Row | None = None) -> dict:
    token = create_access_token(row["id"], row["role"])
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_LIFETIME_SECONDS,
        "user": _safe_user(row, seller),
    }


def _record_user_login(
    connection: sqlite3.Connection,
    user_id: int,
    provider: str,
    created_at: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO user_login_events (user_id, provider, created_at) VALUES (?, ?, ?)",
        (user_id, provider, created_at or datetime.now(timezone.utc).isoformat()),
    )


def _user_and_seller(connection: sqlite3.Connection, user_id: int):
    row = connection.execute(
        """SELECT id, full_name, email, password_hash, role, phone,
                  business_type, whatsapp_number
           FROM users WHERE id = ?""",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your account is no longer available.")
    seller = None
    if row["role"] == "seller":
        seller = connection.execute(
            """
            SELECT id, store_name, store_slug, business_type, whatsapp_number,
                   status, accepted_terms,
                   selected_plan, commission_rate
            FROM sellers WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return row, seller


def _store_slug(store_name: str, user_id: int, connection: sqlite3.Connection) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", store_name.casefold()).strip("-")
    slug = base or f"store-{user_id}"
    if connection.execute("SELECT 1 FROM sellers WHERE store_slug = ?", (slug,)).fetchone():
        slug = f"{slug}-{user_id}"
    return slug


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(registration: AuthRegistration) -> dict:
    ensure_jwt_configured()
    if registration.role == "seller":
        ensure_seller_portal_open()
    if registration.role == "seller" and (
        not registration.store_name or not registration.payout_number
    ):
        raise HTTPException(
            status_code=422,
            detail="Store name and M-Pesa payout number are required for seller accounts.",
        )
    with get_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO users (
                    full_name, email, password_hash, role, phone,
                    business_type, whatsapp_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    registration.full_name,
                    registration.email,
                    password_hash(registration.password),
                    registration.role,
                    registration.phone,
                    registration.business_type or "",
                    registration.whatsapp_number,
                ),
            )
            user_id = cursor.lastrowid
            _record_user_login(connection, user_id, "registration")
            seller = None
            if registration.role == "seller":
                store_slug = _store_slug(registration.store_name, user_id, connection)
                seller_status = (
                    "APPROVED"
                    if auto_approve_seller_registrations_enabled()
                    else "PENDING"
                )
                seller_cursor = connection.execute(
                    """
                    INSERT INTO sellers (
                        user_id, store_name, store_slug, business_phone,
                        payout_method, payout_account, owner_name,
                        business_category, city, business_registration_number,
                        business_type, whatsapp_phone, whatsapp_number,
                        accepted_terms, selected_plan, commission_rate,
                        commission_percentage, commission_is_custom, status
                    ) VALUES (?, ?, ?, ?, 'M-Pesa', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 1, ?)
                    """,
                    (
                        user_id,
                        registration.store_name,
                        store_slug,
                        registration.phone,
                        registration.payout_number,
                        registration.full_name,
                        registration.business_category,
                        registration.city or "",
                        registration.business_registration_number,
                        registration.business_type,
                        registration.whatsapp_number,
                        registration.whatsapp_number,
                        registration.selected_plan,
                        SELLER_PLAN_COMMISSION_RATES[registration.selected_plan],
                        SELLER_PLAN_COMMISSION_RATES[registration.selected_plan],
                        seller_status,
                    ),
                )
                seller_id = seller_cursor.lastrowid
                connection.execute(
                    """
                    INSERT INTO seller_profiles (
                        user_id, seller_id, store_name, store_slug, business_phone,
                        payout_number, business_category,
                        business_registration_number, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        seller_id,
                        registration.store_name,
                        store_slug,
                        registration.phone,
                        registration.payout_number,
                        registration.business_category,
                        registration.business_registration_number,
                        seller_status.casefold(),
                    ),
                )
                seller = connection.execute(
                    """
                    SELECT id, store_name, store_slug, status, accepted_terms,
                           selected_plan, commission_rate
                    FROM sellers WHERE id = ?
                    """,
                    (seller_id,),
                ).fetchone()
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="An account already uses this email address.",
            ) from error
        user, seller = _user_and_seller(connection, user_id)
    return _auth_response(user, seller)


@router.post("/login")
def login_user(credentials: AuthLogin, request: Request) -> dict:
    ensure_jwt_configured()
    ip_address = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=15)).isoformat()
    with get_connection() as connection:
        failed_attempts = connection.execute(
            """
            SELECT COUNT(*) FROM seller_login_attempts
            WHERE ip_address = ? AND succeeded = 0 AND created_at >= ?
            """,
            (ip_address, cutoff),
        ).fetchone()[0]
        if failed_attempts >= 5:
            raise HTTPException(
                status_code=429,
                detail="Too many failed sign-in attempts. Try again in 15 minutes.",
            )
        user = connection.execute(
            """
            SELECT id, full_name, email, password_hash, role, phone,
                   business_type, whatsapp_number
            FROM users WHERE email = ?
            """,
            (credentials.email,),
        ).fetchone()
        valid = user is not None and password_matches(
            credentials.password, user["password_hash"]
        )
        if valid:
            if user["role"] == "seller":
                ensure_seller_portal_open(connection)
            _record_user_login(connection, user["id"], "password", now.isoformat())
        connection.execute(
            """
            INSERT INTO seller_login_attempts (email, ip_address, succeeded, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (credentials.email, ip_address, int(valid), now.isoformat()),
        )
        connection.commit()
        if not valid:
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        _, seller = _user_and_seller(connection, user["id"])
    return _auth_response(user, seller)


def _verify_google_credential(credential: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this server.",
        )
    try:
        response = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=5.0,
        )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail="Google sign-in could not be verified right now.",
        ) from error
    if response.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail="Google sign-in could not be verified right now.",
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="The Google sign-in token is invalid.")
    try:
        identity = response.json()
        if not isinstance(identity, dict):
            raise ValueError("Google returned an invalid identity payload.")
        expires_at = int(identity.get("exp", "0"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401, detail="The Google sign-in token is invalid."
        ) from None
    email_verified = identity.get("email_verified")
    email_verified = email_verified is True or (
        isinstance(email_verified, str) and email_verified.casefold() == "true"
    )
    email = identity.get("email")
    issuer = identity.get("iss")
    if (
        identity.get("aud") != client_id
        or not isinstance(issuer, str)
        or issuer not in {"accounts.google.com", "https://accounts.google.com"}
        or expires_at <= int(datetime.now(timezone.utc).timestamp())
        or not email_verified
        or not isinstance(identity.get("sub"), str)
        or not identity["sub"]
        or not isinstance(email, str)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        raise HTTPException(status_code=401, detail="The Google sign-in token is invalid.")
    return identity


def _login_with_google_demo(request: Request) -> dict:
    environment = os.getenv("APP_ENV", "production").strip().casefold()
    if environment not in {"development", "dev", "local", "testing"}:
        raise HTTPException(
            status_code=403,
            detail="Google simulation sign-in is only available in development.",
        )

    demo_email = "jasonikonya1@gmail.com"
    demo_subject = f"development-google:{demo_email}"
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            """
            SELECT id, full_name, email, password_hash, role, phone,
                   business_type, whatsapp_number, google_subject
            FROM users WHERE email = ?
            """,
            (demo_email,),
        ).fetchone()
        if user is None:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users (
                        full_name, email, password_hash, role, phone, google_subject
                    ) VALUES (?, ?, '', 'buyer', '', ?)
                    """,
                    ("Jason Ikonya", demo_email, demo_subject),
                )
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="The development Google account could not be created.",
                ) from error
            user = connection.execute(
                """
                SELECT id, full_name, email, password_hash, role, phone,
                       business_type, whatsapp_number, google_subject
                FROM users WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
        if user["role"] != "buyer":
            raise HTTPException(
                status_code=403,
                detail="Google sign-in is for buyer accounts only.",
            )
        _record_user_login(connection, user["id"], "google-demo")
        connection.commit()
    return {**_auth_response(user), "provider": "google"}


@router.post("/google")
def login_with_google(credentials: GoogleAuthInput, request: Request) -> dict:
    ensure_jwt_configured()
    if credentials.simulation:
        return _login_with_google_demo(request)
    identity = _verify_google_credential(credentials.credential)
    email = str(identity["email"]).casefold()
    google_subject = str(identity["sub"])
    with get_connection() as connection:
        user = connection.execute(
            """
            SELECT id, full_name, email, password_hash, role, phone,
                   business_type, whatsapp_number, google_subject
            FROM users WHERE google_subject = ?
            """,
            (google_subject,),
        ).fetchone()
        if user is None:
            existing = connection.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="This email already has an account. Sign in with your password first.",
                )
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users (
                        full_name, email, password_hash, role, phone, google_subject
                    ) VALUES (?, ?, '', 'buyer', '', ?)
                    """,
                    (
                        str(identity.get("name") or email.split("@", 1)[0])[:120],
                        email,
                        google_subject,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="This Google account could not be linked to a buyer account.",
                ) from error
            user = connection.execute(
                """
                SELECT id, full_name, email, password_hash, role, phone,
                       business_type, whatsapp_number, google_subject
                FROM users WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
        if user["role"] != "buyer":
            raise HTTPException(status_code=403, detail="Google sign-in is for buyers only.")
        _record_user_login(connection, user["id"], "google")
        connection.commit()
    return {**_auth_response(user), "provider": "google"}


@router.get("/me")
def current_user(request: Request) -> dict:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign-in is required.")
    claims = decode_access_token(token)
    with get_connection() as connection:
        user, seller = _user_and_seller(connection, int(claims["sub"]))
    if user["role"] != claims["role"]:
        raise HTTPException(status_code=401, detail="Your sign-in has expired.")
    return _safe_user(user, seller)
