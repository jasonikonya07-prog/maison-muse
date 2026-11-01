import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import HTTPException, status


PASSWORD_ITERATIONS = 310_000
JWT_ISSUER = "maison-muse"
JWT_LIFETIME_SECONDS = 12 * 60 * 60


def password_hash(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), actual_salt, PASSWORD_ITERATIONS
    )
    return f"{actual_salt.hex()}:{digest.hex()}"


def password_matches(password: str, stored_hash: str) -> bool:
    if ":" not in stored_hash:
        return False
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        candidate = password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest_hex)


def _jwt_secret() -> bytes:
    secret = os.getenv("AUTH_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )
    return secret.encode("utf-8")


def ensure_jwt_configured() -> None:
    _jwt_secret()


def _encode_segment(value: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=").decode("ascii")


def create_access_token(user_id: int, role: str) -> str:
    now = int(time.time())
    header = _encode_segment({"alg": "HS256", "typ": "JWT"})
    payload = _encode_segment(
        {
            "exp": now + JWT_LIFETIME_SECONDS,
            "iat": now,
            "iss": JWT_ISSUER,
            "role": role,
            "sub": str(user_id),
        }
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(_jwt_secret(), signing_input, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.{encoded_signature}"


def decode_access_token(token: str) -> dict:
    try:
        if len(token) > 8192:
            raise ValueError("Token is too large.")
        header_segment, payload_segment, signature_segment = token.split(".")
        header = json.loads(
            base64.urlsafe_b64decode(header_segment + "=" * (-len(header_segment) % 4))
        )
        payload = json.loads(
            base64.urlsafe_b64decode(payload_segment + "=" * (-len(payload_segment) % 4))
        )
        signature = base64.urlsafe_b64decode(
            signature_segment + "=" * (-len(signature_segment) % 4)
        )
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected = hmac.new(_jwt_secret(), signing_input, hashlib.sha256).digest()
        if (
            not isinstance(header, dict)
            or not isinstance(payload, dict)
            or header.get("alg") != "HS256"
            or not hmac.compare_digest(signature, expected)
        ):
            raise ValueError("Invalid token signature.")
        subject = payload["sub"]
        role = payload["role"]
        issued_at = int(payload["iat"])
        if (
            payload.get("iss") != JWT_ISSUER
            or role not in {"buyer", "seller", "admin"}
            or not isinstance(subject, str)
            or not subject.isdigit()
            or int(payload["exp"]) <= int(time.time())
            or issued_at > int(time.time()) + 60
        ):
            raise ValueError("Invalid token claims.")
        return payload
    except HTTPException:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your sign-in has expired. Please sign in again.",
        ) from None
