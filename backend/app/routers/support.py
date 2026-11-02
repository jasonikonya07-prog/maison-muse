import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
)
from fastapi import WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.admin_auth import current_admin_details
from app.auth_security import decode_access_token
from app.config import get_database_url
from app.data_encryption import phone_lookup_hash
from app.database import get_connection


router = APIRouter()
websocket_router = APIRouter()
SUPPORT_STATUSES = {"BOT", "WAITING_AGENT", "RESOLVED"}
SUBSCRIPTION_REPLY = (
    "Maison Muse offers 3 flexible Seller Tiers: "
    "1️⃣ Boutique Starter: Free monthly fee (10% platform commission per sale). "
    "2️⃣ Pro Studio: KSh 2,500/month (5% commission + Priority Search Boosting). "
    "3️⃣ Enterprise: KSh 7,500/month (2.5% commission + Dedicated Account Manager). "
    "You can upgrade or switch plans anytime inside your Seller Studio under "
    "'Subscription & Membership'."
)
FARMER_REPLY = (
    "For Farmers & Livestock Sellers: Agricultural listings (cattle, goats, poultry, "
    "veterinary medicines) bypass platform escrow fees completely! Buyers connect "
    "directly with you on your verified WhatsApp Business line to finalize transactions."
)
PAYMENT_REPLY = (
    "All storefront purchases are secured via M-Pesa STK push. For standard sellers, "
    "funds are held in secure escrow until the buyer confirms delivery. You can trigger "
    "instant B2C withdrawals to your phone, Till, or Paybill directly from your "
    "Financial Ledger."
)
TRACKING_REPLY = (
    "You can track any order in real time! Enter your Tracking ID on the storefront "
    "search bar or visit the Order Tracking page (`/orders/:trackingId`). You'll see "
    "live progress from packing to courier delivery."
)
ORDER_CANCEL_REPLY = (
    "I can’t cancel or change an order automatically. I’ve sent your request to "
    "Maison Muse Support so an agent can review it. Please include only your order "
    "number if you have it—never send a password, one-time code, PIN, or payment "
    "details. Do not place a second order while you wait for confirmation."
)
REFUND_RETURN_REPLY = (
    "Refunds and returns need a support review, and I can’t approve or issue one "
    "automatically. I’ve sent your request to a support agent. Keep your order "
    "number available, but don’t share passwords, one-time codes, PINs, or full "
    "payment details in chat."
)
DELIVERY_ISSUE_REPLY = (
    "For a delayed or missing delivery, check the latest steps on the Order Tracking "
    "page using your tracking ID. If the estimate has passed or tracking has stopped, "
    "I’ve sent this to a support agent to investigate."
)
ACCOUNT_ACCESS_REPLY = (
    "For sign-in trouble, use the account sign-in page and its password recovery "
    "option. Support will never ask you to send your password, PIN, one-time code, "
    "or full payment details in chat."
)
PRIVACY_REPLY = (
    "For your safety, I don’t handle or reveal passwords, one-time codes, PINs, "
    "full card or bank details, or private account data. That content was not saved "
    "as a chat message. Please resend your question without those details; never "
    "share a password or verification code with anyone."
)
VERIFICATION_REPLY = (
    "Every seller on Maison Muse undergoes KYC verification. Click on any green "
    "'Verified Seller' badge or use Verify Seller to inspect their verification "
    "status, public store details, trust indicators, and verified buyer reviews. "
    "I can’t reveal private contact or account information."
)
FALLBACK_REPLY = (
    "I couldn't match that to a topic yet. Ask about Seller Plans, M-Pesa, or connect "
    "with a live admin using one of the options below."
)
FALLBACK_ACTIONS = [
    {"intent": "seller_plans", "label": "Ask about Seller Plans"},
    {"intent": "mpesa_help", "label": "Ask about M-Pesa"},
    {"intent": "human", "label": "Connect with Live Admin"},
]
SUPPORT_INTENT_PATTERNS = (
    (
        "order_cancel",
        r"\b(?:cancel|cancell?ation|stop|void)\b.{0,50}\b(?:my\s+)?orders?\b|"
        r"\b(?:orders?)\b.{0,50}\b(?:cancel|cancell?ation|stop|void)\b",
    ),
    (
        "refund_return",
        r"\b(?:refund|return|exchange|money\s+back|charged\s+twice)\b",
    ),
    (
        "delivery_problem",
        r"\b(?:late|delayed|missing|lost|not\s+arrived|never\s+arrived)\b.{0,40}"
        r"\b(?:delivery|order|package|parcel|courier)\b|"
        r"\b(?:delivery|order|package|parcel|courier)\b.{0,40}"
        r"\b(?:late|delayed|missing|lost|not\s+arrived|never\s+arrived)\b",
    ),
    (
        "account_access",
        r"\b(?:can'?t|cannot|unable\s+to|trouble\s+)?(?:log\s*in|sign\s*in|"
        r"access\s+my\s+account|forgot\s+my\s+password)\b",
    ),
    (
        "privacy",
        r"\b(?:show|tell|give|reveal|find|what\s+is)\b.{0,50}\b(?:private|personal|"
        r"someone\s+else'?s?\s+(?:order|account|phone|address|email)|phone\s+number|"
        r"home\s+address|password|"
        r"passcode|one[\s-]*time\s+(?:password|code|pin)|otp|verification\s+code|"
        r"security\s+code|pin|cvv|cvc|bank\s+account|card\s+number|private\s+key|"
        r"seed\s+phrase|national\s+id|someone\s+else'?s?\s+(?:order|account))\b",
    ),
    (
        "seller_plans",
        r"\b(?:monthly|subscription|pricing|plans?|commission|fees?|tier|"
        r"how\s+much\s+to\s+sell)\b",
    ),
    (
        "farmer_whatsapp",
        r"\b(?:farmer|cow|goat|poultry|dawa\s+ya\s+minyoo|livestock|"
        r"agriculture|whatsapp)\b",
    ),
    (
        "mpesa_help",
        r"\b(?:m[\s-]?pesa|stk|pay(?:ing|ment|ments)?|withdraw|escrow|payout|"
        r"till|paybill)\b",
    ),
    (
        "order_status",
        r"\b(?:track(?:ing)?|order(?:s)?(?:\s+status)?|delivery|deliveries|"
        r"fargo|bodaboda|shipping|where\s+is\s+my\s+item)\b",
    ),
    (
        "seller_verification",
        r"\b(?:verify|verified|verification|badge|trust|scam|phone\s+number|"
        r"is\s+(?:this\s+)?seller\s+real)\b",
    ),
)
SENSITIVE_SUPPORT_CONTENT_PATTERNS = (
    r"\b(?:password|passcode|pin|otp|one[\s-]*time\s+(?:password|code|pin)|"
    r"verification\s+code|security\s+code)\s*(?:is|:|=)\s*[A-Za-z0-9@#$%^&*!_-]{4,}",
    r"\b(?:credit|debit)?\s*card(?:\s*number)?\D{0,12}(?:\d[ -]?){13,19}\b",
    r"\b(?:cvv|cvc|security\s+code)\D{0,5}\d{3,4}\b",
    r"\b(?:bank\s+account|account\s+number|national\s+id|passport\s+number)"
    r"\D{0,8}[A-Z0-9-]{6,}\b",
    r"\b(?:api\s+key|private\s+key|seed\s+phrase)\s*(?:is|:|=)\s*\S{8,}",
)
REDACTED_SENSITIVE_MESSAGE = (
    "[Message hidden for safety because it contained sensitive information.]"
)
SUPPORT_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
)
SUPPORT_PHONE_PATTERN = re.compile(
    r"(?<![A-Z0-9-])(?:\+?254|0)(?:[\s().-]*\d){8,10}(?![A-Z0-9-])",
    re.IGNORECASE,
)
ALLOWED_ATTACHMENT_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
    "application/pdf": (b"%PDF-",),
}


class SupportCartItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    quantity: int = Field(ge=1, le=99)


class SupportAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    content_type: str
    data_url: str = Field(min_length=30, max_length=2_800_000)

    @model_validator(mode="after")
    def validate_file_content(self):
        signatures = ALLOWED_ATTACHMENT_SIGNATURES.get(self.content_type)
        if not signatures:
            raise ValueError("Attach a PNG, JPEG, WebP image, or PDF file.")
        expected_prefix = f"data:{self.content_type};base64,"
        if not self.data_url.startswith(expected_prefix):
            raise ValueError("The attachment data is invalid.")
        try:
            content = base64.b64decode(
                self.data_url[len(expected_prefix) :], validate=True
            )
        except (binascii.Error, ValueError):
            raise ValueError("The attachment data is invalid.") from None
        signature_matches = any(content.startswith(item) for item in signatures)
        if self.content_type == "image/webp":
            signature_matches = (
                len(content) >= 12
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            )
        if not signature_matches or len(content) > 2 * 1024 * 1024:
            raise ValueError("Attachment must be a valid supported file up to 2 MB.")
        return self


class SupportMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticket_id: str | None = Field(default=None, min_length=36, max_length=36)
    message: str = Field(default="", max_length=2000)
    intent: Literal[
        "message",
        "order_status",
        "order_cancel",
        "refund_return",
        "delivery_problem",
        "account_access",
        "privacy",
        "seller_signup",
        "seller_plans",
        "farmer_whatsapp",
        "seller_verification",
        "mpesa_help",
        "human",
    ] = "message"
    customer_name: str = Field(default="", max_length=120)
    customer_email: str = Field(default="", max_length=254)
    customer_phone: str = Field(default="", max_length=32)
    cart_items: list[SupportCartItem] = Field(default_factory=list, max_length=20)
    attachments: list[SupportAttachment] = Field(default_factory=list, max_length=1)

    @field_validator("ticket_id")
    @classmethod
    def validate_ticket_id(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                uuid.UUID(value)
            except ValueError:
                raise ValueError("The support conversation is invalid.") from None
        return value

    @field_validator("customer_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.attachments and self.intent == "message":
            raise ValueError("Enter a message or attach a supported file.")
        return self


class AdminReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticket_id: str = Field(min_length=36, max_length=36)
    message: str = Field(min_length=1, max_length=2000)


class TicketStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["BOT", "WAITING_AGENT", "RESOLVED"]


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "sender_type": row["sender_type"],
        "sender_name": row["sender_name"],
        "message": row["message"],
        "attachments": json.loads(row["attachments_json"]),
        "timestamp": row["timestamp"],
    }


def _ticket_messages(connection: sqlite3.Connection, ticket_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT id, sender_type, sender_name, message, attachments_json, timestamp
        FROM support_messages WHERE ticket_id = ?
        ORDER BY id
        """,
        (ticket_id,),
    ).fetchall()
    return [_message_payload(row) for row in rows]


def _add_message(
    connection: sqlite3.Connection,
    ticket_id: str,
    sender_type: str,
    message: str,
    sender_name: str = "",
    attachments: list[dict] | None = None,
) -> dict:
    now = _timestamp()
    cursor = connection.execute(
        """
        INSERT INTO support_messages (
            ticket_id, sender_type, sender_name, message, attachments_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            sender_type,
            sender_name,
            message,
            json.dumps(attachments or []),
            now,
        ),
    )
    connection.execute(
        "UPDATE support_tickets SET updated_at = ? WHERE id = ?",
        (now, ticket_id),
    )
    return {
        "id": cursor.lastrowid,
        "sender_type": sender_type,
        "sender_name": sender_name,
        "message": message,
        "attachments": attachments or [],
        "timestamp": now,
    }


def _authenticated_user_id(request: Request) -> int | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        return None
    try:
        claims = decode_access_token(token)
    except HTTPException:
        return None
    return int(claims["sub"])


def _ensure_ticket(
    connection: sqlite3.Connection,
    payload: SupportMessageInput,
    token: str,
    user_id: int | None,
) -> tuple[sqlite3.Row, str]:
    if payload.ticket_id:
        ticket = connection.execute(
            "SELECT * FROM support_tickets WHERE id = ?", (payload.ticket_id,)
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        token_matches = hmac.compare_digest(
            ticket["guest_session_id"], _token_digest(token)
        ) if token else False
        authenticated_owner = user_id is not None and ticket["user_id"] == user_id
        if not authenticated_owner and not token_matches:
            raise HTTPException(
                status_code=403, detail="You cannot access this support conversation."
            )
        return ticket, False

    issued_token = secrets.token_urlsafe(32)
    ticket_id = str(uuid.uuid4())
    customer_name = payload.customer_name
    customer_email = payload.customer_email
    customer_phone = payload.customer_phone
    if user_id is not None:
        user = connection.execute(
            "SELECT full_name, email, phone FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is not None:
            customer_name = customer_name or user["full_name"]
            customer_email = customer_email or user["email"]
            customer_phone = customer_phone or user["phone"]
    cursor = connection.execute(
        """
        INSERT INTO support_tickets (
            id, user_id, guest_session_id, customer_name, customer_email,
            customer_phone, cart_snapshot_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'BOT')
        """,
        (
            ticket_id,
            user_id,
            _token_digest(issued_token),
            customer_name,
            customer_email,
            customer_phone,
            json.dumps([item.model_dump() for item in payload.cart_items]),
        ),
    )
    ticket = connection.execute(
        "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)
    ).fetchone()
    return ticket, issued_token


def _classify_support_intent(intent: str, message: str) -> str:
    if intent == "human":
        return "human"
    if intent in {
        "seller_plans",
        "farmer_whatsapp",
        "mpesa_help",
        "seller_verification",
        "order_cancel",
        "refund_return",
        "delivery_problem",
        "account_access",
        "privacy",
    }:
        return intent
    for candidate, pattern in SUPPORT_INTENT_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return candidate
    if intent == "order_status":
        return "order_status"
    if intent == "seller_signup" or re.search(
        r"\b(?:sell|selling|seller|register|registration|store|shop|vendor)\b",
        message,
        re.IGNORECASE,
    ):
        return "seller_signup"
    return "fallback"


def _contains_sensitive_support_content(message: str) -> bool:
    return any(
        re.search(pattern, message, re.IGNORECASE)
        for pattern in SENSITIVE_SUPPORT_CONTENT_PATTERNS
    )


def _redact_support_contact_info(message: str) -> str:
    without_emails = SUPPORT_EMAIL_PATTERN.sub("[contact details removed]", message)
    return SUPPORT_PHONE_PATTERN.sub("[contact details removed]", without_emails)


def _automated_reply(
    connection, intent: str, message: str, user_id: int | None = None
) -> tuple[str, list[dict]]:
    classified_intent = _classify_support_intent(intent, message)
    if classified_intent == "privacy":
        return PRIVACY_REPLY, []
    if classified_intent == "order_cancel":
        return ORDER_CANCEL_REPLY, []
    if classified_intent == "refund_return":
        return REFUND_RETURN_REPLY, []
    if classified_intent == "delivery_problem":
        return DELIVERY_ISSUE_REPLY, []
    if classified_intent == "account_access":
        return ACCOUNT_ACCESS_REPLY, []

    normalized = message.strip().upper()
    if normalized and normalized != "WHERE IS MY ORDER?":
        order = connection.execute(
            """
            SELECT order_number, status, gateway_tracking_id
            FROM orders
            WHERE order_number = ? OR gateway_tracking_id = ?
            LIMIT 1
            """,
            (normalized, normalized),
        ).fetchone()
    elif intent == "order_status" and user_id is not None:
        user = connection.execute(
            "SELECT phone FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        matching_orders = (
            _orders_for_customer_phone(connection, user["phone"], limit=1)
            if user and user["phone"]
            else []
        )
        order = matching_orders[0] if matching_orders else None
    else:
        order = None
    if order:
        return (
            f"Order {order['order_number']} is currently "
            f"{order['status'].replace('_', ' ').title()}. "
            "For payment or account details, sign in securely or contact support.",
            [],
        )

    if classified_intent == "seller_plans":
        return SUBSCRIPTION_REPLY, []
    if classified_intent == "farmer_whatsapp":
        return FARMER_REPLY, []
    if classified_intent == "mpesa_help":
        return PAYMENT_REPLY, []
    if classified_intent == "order_status":
        return TRACKING_REPLY, []
    if classified_intent == "seller_verification":
        return VERIFICATION_REPLY, []
    if classified_intent == "human":
        return (
            "I’m connecting you with a live support agent. You can keep messaging here.",
            [],
        )
    if classified_intent == "seller_signup":
        return (
            "To sell on Maison Muse, choose “Sell with Maison Muse” from the storefront "
            "account menu and complete the seller registration form. Your shop is reviewed "
            "before listings go live.",
            [],
        )

    if len(normalized) >= 6 and any(character.isdigit() for character in normalized):
        return (
            "I couldn’t find an order matching that reference. Please double-check the "
            "order number, or choose “Talk to a Live Support Agent” for help.",
            [],
        )
    return FALLBACK_REPLY, FALLBACK_ACTIONS


def _orders_for_customer_phone(
    connection, phone: str, *, limit: int
):
    if get_database_url():
        return connection.execute(
            """
            SELECT order_number, status, payment_status, gateway_tracking_id,
                   created_at
            FROM orders
            WHERE customer_phone_lookup_hash = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (phone_lookup_hash(phone), limit),
        ).fetchall()
    return connection.execute(
        """
        SELECT order_number, status, payment_status, gateway_tracking_id, created_at
        FROM orders
        WHERE customer_phone = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (phone, limit),
    ).fetchall()


def _require_support_admin(request: Request, right: str) -> dict:
    identity = current_admin_details(request)
    if identity is None:
        raise HTTPException(status_code=401, detail="Admin sign-in is required.")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT permissions_json FROM admin_role_permissions WHERE role = ?",
            (identity["role"],),
        ).fetchone()
    permissions = json.loads(row["permissions_json"]) if row else {}
    if not permissions.get("support", {}).get(right, False):
        raise HTTPException(
            status_code=403,
            detail=f"Your {identity['role']} role does not have {right} access to support.",
        )
    request.state.admin_identity = identity
    return identity


def _verify_admin_write(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in request.app.state.cors_origins:
        raise HTTPException(
            status_code=403,
            detail="Admin requests must come from an approved storefront origin.",
        )
    if request.headers.get("x-admin-request") != "1":
        raise HTTPException(
            status_code=403, detail="The admin request validation header is required."
        )


async def _broadcast(request: Request, ticket_id: str, event: dict) -> None:
    manager = request.app.state.support_connections
    await manager.broadcast(ticket_id, event)


@router.post("/support/message")
async def send_support_message(
    payload: SupportMessageInput,
    request: Request,
    response: Response,
    support_token: str = Header(default="", alias="X-Support-Token"),
) -> dict:
    user_id = _authenticated_user_id(request)
    contains_sensitive_content = _contains_sensitive_support_content(payload.message)
    safe_message = (
        REDACTED_SENSITIVE_MESSAGE
        if contains_sensitive_content
        else _redact_support_contact_info(payload.message.strip())
    )
    attachments = (
        []
        if contains_sensitive_content
        else [item.model_dump() for item in payload.attachments]
    )
    classified_intent = (
        "privacy"
        if contains_sensitive_content
        else _classify_support_intent(payload.intent, payload.message)
    )
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        ticket, issued_token = _ensure_ticket(
            connection, payload, support_token, user_id
        )
        is_human_request = payload.intent == "human" or classified_intent in {
            "order_cancel",
            "refund_return",
            "delivery_problem",
        }
        status_value = (
            "WAITING_AGENT"
            if is_human_request
            else "BOT"
            if ticket["status"] == "RESOLVED"
            else ticket["status"]
        )
        connection.execute(
            "UPDATE support_tickets SET status = ?, updated_at = ? WHERE id = ?",
            (status_value, _timestamp(), ticket["id"]),
        )
        user_message = None
        if safe_message or attachments:
            user_message = _add_message(
                connection,
                ticket["id"],
                "USER",
                safe_message,
                ticket["customer_name"] or "Customer",
                attachments,
            )
        bot_message = None
        if user_message and status_value in {"BOT", "WAITING_AGENT"}:
            reply_text, suggested_actions = _automated_reply(
                connection,
                classified_intent,
                (
                    "I shared sensitive information."
                    if contains_sensitive_content
                    else safe_message
                ),
                ticket["user_id"],
            )
            bot_message = _add_message(
                connection,
                ticket["id"],
                "BOT",
                reply_text,
                "Maison Muse Support Bot",
            )
            if suggested_actions:
                bot_message["suggested_actions"] = suggested_actions
        connection.commit()
        current_ticket = connection.execute(
            "SELECT * FROM support_tickets WHERE id = ?", (ticket["id"],)
        ).fetchone()
        messages = _ticket_messages(connection, ticket["id"])

    if issued_token:
        response.set_cookie(
            f"maison_muse_support_{ticket['id']}",
            issued_token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path=f"/ws/support/{ticket['id']}",
        )
    for message in (user_message, bot_message):
        if message:
            await _broadcast(
                request,
                ticket["id"],
                {"type": "message", "message": message},
            )
    await _broadcast(
        request,
        ticket["id"],
        {"type": "status", "status": status_value},
    )
    return {
        "ticket_id": ticket["id"],
        "status": current_ticket["status"],
        "access_token": issued_token or support_token,
        "messages": messages,
        "bot_reply": bot_message,
    }


@router.get("/support/tickets/{ticket_id}")
def get_customer_support_ticket(
    ticket_id: str,
    support_token: str = Header(default="", alias="X-Support-Token"),
) -> dict:
    with get_connection() as connection:
        ticket = connection.execute(
            "SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        if not support_token or not hmac.compare_digest(
            ticket["guest_session_id"], _token_digest(support_token)
        ):
            raise HTTPException(
                status_code=403, detail="You cannot access this support conversation."
            )
        return {
            "ticket_id": ticket["id"],
            "status": ticket["status"],
            "messages": _ticket_messages(connection, ticket_id),
        }


@router.get("/admin/support/tickets")
def list_support_tickets(
    request: Request,
    status_filter: str = Query(default="all", alias="status"),
) -> list[dict]:
    _require_support_admin(request, "read")
    if status_filter != "all" and status_filter not in SUPPORT_STATUSES:
        raise HTTPException(status_code=422, detail="Choose a valid support status.")
    with get_connection() as connection:
        query = """
            SELECT t.*, u.full_name AS account_name, u.email AS account_email,
                   u.phone AS account_phone
            FROM support_tickets t
            LEFT JOIN users u ON u.id = t.user_id
        """
        parameters: tuple[str, ...] = ()
        if status_filter != "all":
            query += " WHERE t.status = ?"
            parameters = (status_filter,)
        query += " ORDER BY CASE t.status WHEN 'WAITING_AGENT' THEN 0 "
        query += "WHEN 'BOT' THEN 1 ELSE 2 END, t.updated_at DESC LIMIT 200"
        tickets = connection.execute(query, parameters).fetchall()
        results = []
        for ticket in tickets:
            message_count = connection.execute(
                "SELECT COUNT(*) FROM support_messages WHERE ticket_id = ?",
                (ticket["id"],),
            ).fetchone()[0]
            last_message_row = connection.execute(
                """
                SELECT id, sender_type, sender_name, message, timestamp
                FROM support_messages WHERE ticket_id = ? ORDER BY id DESC LIMIT 1
                """,
                (ticket["id"],),
            ).fetchone()
            summary_message = dict(last_message_row) if last_message_row else None
            phone = ticket["account_phone"] or ticket["customer_phone"]
            orders = (
                [dict(order) for order in _orders_for_customer_phone(connection, phone, limit=5)]
                if phone
                else []
            )
            results.append(
                {
                    "id": ticket["id"],
                    "user_id": ticket["user_id"],
                    "status": ticket["status"],
                    "customer": {
                        "name": ticket["account_name"] or ticket["customer_name"],
                        "email": ticket["account_email"] or ticket["customer_email"],
                        "phone": phone or "",
                        "authenticated": ticket["user_id"] is not None,
                    },
                    "cart_items": json.loads(ticket["cart_snapshot_json"]),
                    "orders": orders,
                    "created_at": ticket["created_at"],
                    "updated_at": ticket["updated_at"],
                    "message_count": message_count,
                    "last_message": summary_message,
                }
            )
        return results


@router.get("/admin/support/tickets/{ticket_id}")
def get_admin_support_ticket(ticket_id: str, request: Request) -> dict:
    _require_support_admin(request, "read")
    with get_connection() as connection:
        ticket = connection.execute(
            """
            SELECT t.*, u.full_name AS account_name, u.email AS account_email,
                   u.phone AS account_phone
            FROM support_tickets t
            LEFT JOIN users u ON u.id = t.user_id
            WHERE t.id = ?
            """,
            (ticket_id,),
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        phone = ticket["account_phone"] or ticket["customer_phone"]
        orders = (
            [
                dict(order)
                for order in _orders_for_customer_phone(connection, phone, limit=5)
            ]
            if phone
            else []
        )
        return {
            "id": ticket["id"],
            "user_id": ticket["user_id"],
            "status": ticket["status"],
            "customer": {
                "name": ticket["account_name"] or ticket["customer_name"],
                "email": ticket["account_email"] or ticket["customer_email"],
                "phone": phone or "",
                "authenticated": ticket["user_id"] is not None,
            },
            "cart_items": json.loads(ticket["cart_snapshot_json"]),
            "orders": orders,
            "created_at": ticket["created_at"],
            "updated_at": ticket["updated_at"],
            "messages": _ticket_messages(connection, ticket_id),
        }


@router.post("/admin/support/reply", status_code=201)
async def send_admin_support_reply(
    payload: AdminReplyInput, request: Request
) -> dict:
    _verify_admin_write(request)
    identity = _require_support_admin(request, "write")
    with get_connection() as connection:
        ticket = connection.execute(
            "SELECT id, status FROM support_tickets WHERE id = ?",
            (payload.ticket_id,),
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        message = _add_message(
            connection,
            ticket["id"],
            "ADMIN",
            payload.message,
            "Admin Support",
        )
        connection.execute(
            "UPDATE support_tickets SET status = 'WAITING_AGENT' WHERE id = ?",
            (ticket["id"],),
        )
        connection.commit()
    await _broadcast(
        request, payload.ticket_id, {"type": "message", "message": message}
    )
    await _broadcast(
        request,
        payload.ticket_id,
        {"type": "status", "status": "WAITING_AGENT"},
    )
    return message


@router.patch("/admin/support/tickets/{ticket_id}/status")
async def update_support_ticket_status(
    ticket_id: str, payload: TicketStatusInput, request: Request
) -> dict:
    _verify_admin_write(request)
    _require_support_admin(request, "write")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE support_tickets SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (payload.status, _timestamp(), ticket_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        connection.commit()
    await _broadcast(
        request,
        ticket_id,
        {"type": "status", "status": payload.status},
    )
    return {"ticket_id": ticket_id, "status": payload.status}


@websocket_router.websocket("/ws/support/{ticket_id}")
async def support_websocket(websocket: WebSocket, ticket_id: str) -> None:
    origin = websocket.headers.get("origin")
    if origin and origin not in websocket.app.state.cors_origins:
        await websocket.close(code=4403, reason="Origin is not allowed.")
        return
    identity = current_admin_details(websocket)
    access_token = websocket.cookies.get(f"maison_muse_support_{ticket_id}", "")
    try:
        with get_connection() as connection:
            ticket = connection.execute(
                "SELECT guest_session_id FROM support_tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            admin_allowed = False
            if identity:
                permissions = connection.execute(
                    "SELECT permissions_json FROM admin_role_permissions WHERE role = ?",
                    (identity["role"],),
                ).fetchone()
                admin_allowed = bool(
                    permissions
                    and json.loads(permissions["permissions_json"])
                    .get("support", {})
                    .get("read", False)
                )
            customer_allowed = bool(
                ticket
                and access_token
                and hmac.compare_digest(
                    ticket["guest_session_id"], _token_digest(access_token)
                )
            )
    except HTTPException:
        await websocket.close(code=4401, reason="Sign-in is required.")
        return
    if ticket is None or not (admin_allowed or customer_allowed):
        await websocket.close(
            code=4401 if ticket else 4404,
            reason="Support conversation access is unavailable.",
        )
        return

    manager = websocket.app.state.support_connections
    await manager.connect(ticket_id, websocket, is_admin=admin_allowed)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        was_admin = manager.disconnect(ticket_id, websocket)
        if was_admin:
            await manager.broadcast(
                ticket_id,
                {
                    "type": "presence",
                    "agents_online": len(manager.admin_connections.get(ticket_id, set())),
                },
            )
