import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from app.auth_security import (
    decode_access_token,
    password_hash as _password_hash,
    password_matches as _password_matches,
)
from app.config import (
    UPLOAD_ROOT,
    auto_approve_seller_registrations_enabled,
    demo_seller_approval_enabled,
)
from app.database import get_connection
from app.email_delivery import send_email
from app.order_tracking import (
    apply_seller_fulfillment,
    effective_fulfillment_status,
    publish_order_update,
    status_timeline,
)
from app.routers.products import expire_seller_promotions, serialize_product
from app.schemas import (
    AGRICULTURE_BUSINESS_TYPE,
    AGRICULTURE_PRODUCT_CATEGORIES,
    SellerFulfillmentUpdate,
    SellerLogin,
    SellerPlanUpdate,
    SellerPlanUpgrade,
    SellerProfileUpdateRequest,
    SellerProfileUpdateVerify,
    SellerProductBulkInput,
    SellerProductInput,
    SellerRegistration,
    SellerStorefrontUpdate,
    SellerWithdrawalInput,
)


router = APIRouter()
SELLER_COOKIE_NAME = "maison_muse_seller"
SESSION_HOURS = 12
PLAN_RATES = {"boutique": 10.0, "pro": 5.0, "enterprise": 2.5}
PLAN_PRICES = {"boutique": 0.0, "pro": 2500.0, "enterprise": 7500.0}
logger = logging.getLogger(__name__)


def _deliver_seller_update_code(
    recipient: str, code: str, changed_email: bool, changed_phone: bool
) -> None:
    changes = []
    if changed_email:
        changes.append("business email")
    if changed_phone:
        changes.append("business phone / M-Pesa line")
    text = (
        "Use this one-time code to confirm your Maison Muse seller profile update:\n\n"
        f"{code}\n\n"
        f"Requested changes: {', '.join(changes)}.\n"
        "The code expires in 10 minutes. If you did not request this change, ignore this email."
    )
    delivery = send_email(
        recipient,
        "Confirm your Maison Muse seller profile update",
        text,
    )
    if delivery != "SENT":
        raise HTTPException(
            status_code=503,
            detail=(
                "Profile verification email is not configured."
                if delivery == "NOT_CONFIGURED"
                else "Could not send the profile verification email. Please try again."
            ),
        )


def _seller_payload(row: sqlite3.Row, include_payout: bool = False) -> dict:
    seller = {
        "id": row["id"],
        "user_id": row["user_id"],
        "email": row["email"],
        "store_name": row["store_name"],
        "store_bio": row["store_bio"],
        "business_category": row["business_category"],
        "business_type": row["business_type"],
        "owner_name": row["owner_name"],
        "submitted_documents": json.loads(row["submitted_documents_json"]),
        "review_note": row["review_note"],
        "review_state": row["review_state"],
        "maintenance_mode": bool(row["maintenance_mode"]),
        "maintenance_reason": row["maintenance_reason"],
        "store_slug": row["store_slug"],
        "logo_url": row["logo_url"],
        "banner_url": row["banner_url"],
        "business_phone": row["business_phone"],
        "whatsapp_phone": row["whatsapp_phone"],
        "whatsapp_number": row["whatsapp_number"],
        "instagram_url": row["instagram_url"],
        "tiktok_url": row["tiktok_url"],
        "operating_hours": row["operating_hours"],
        "holiday_mode": bool(row["holiday_mode"]),
        "payout_method": row["payout_method"],
        "status": row["status"],
        "rating": row["rating"],
        "commission_percentage": row["commission_percentage"],
        "accepted_terms": bool(row["accepted_terms"]),
        "selected_plan": row["selected_plan"],
        "commission_rate": row["commission_rate"],
    }
    if include_payout:
        seller["payout_account"] = row["payout_account"]
    return seller


def _set_seller_session(user_id: int, response: Response) -> None:
    raw_token = secrets.token_urlsafe(32)
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO seller_sessions (session_id, user_id, token_hash, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_id, token_hash, expires_at),
        )
        connection.commit()
    response.set_cookie(
        SELLER_COOKIE_NAME,
        raw_token,
        httponly=True,
        secure=os.getenv("ADMIN_COOKIE_SECURE", "false").strip().casefold() == "true",
        samesite="lax",
        max_age=SESSION_HOURS * 60 * 60,
        path="/",
    )


def require_seller(
    request: Request,
    approved: bool = False,
    allow_suspended: bool = False,
) -> sqlite3.Row:
    authorization = request.headers.get("authorization", "")
    scheme, _, access_token = authorization.partition(" ")
    if scheme.casefold() == "bearer" and access_token:
        claims = decode_access_token(access_token)
        if claims["role"] != "seller":
            raise HTTPException(
                status_code=403, detail="A seller account is required for this resource."
            )
        with get_connection() as connection:
            seller = connection.execute(
                """
                SELECT s.*, u.email, NULL AS session_id
                FROM sellers s JOIN users u ON u.id = s.user_id
                WHERE s.user_id = ? AND u.role = 'seller'
                """,
                (int(claims["sub"]),),
            ).fetchone()
    else:
        raw_token = request.cookies.get(SELLER_COOKIE_NAME, "")
        if not raw_token:
            raise HTTPException(status_code=401, detail="Seller sign-in is required.")
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            seller = connection.execute(
                """
                SELECT s.*, u.email, ss.session_id
                FROM seller_sessions ss
                JOIN users u ON u.id = ss.user_id
                JOIN sellers s ON s.user_id = u.id
                WHERE ss.token_hash = ? AND ss.revoked_at IS NULL
                  AND ss.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
    if seller is None:
        raise HTTPException(status_code=401, detail="Seller session has expired.")
    if seller["status"] == "SUSPENDED" and not allow_suspended:
        reason = seller["review_note"].strip() or "No additional reason was provided."
        raise HTTPException(
            status_code=403,
            detail=f"Your seller account is suspended. Reason: {reason}",
        )
    if approved and (
        seller["status"] != "APPROVED" or seller["review_state"] == "UNDER_AUDIT"
    ):
        raise HTTPException(
            status_code=403,
            detail="Your seller account must be approved before managing the store.",
        )
    if approved and seller["maintenance_mode"]:
        reason = seller["maintenance_reason"].strip() or "No additional reason was provided."
        raise HTTPException(
            status_code=403,
            detail=f"Your seller store is under maintenance. Reason: {reason}",
        )
    request.state.seller = seller
    return seller


def _verify_seller_write(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in request.app.state.cors_origins:
        raise HTTPException(
            status_code=403,
            detail="Seller requests must come from an approved storefront origin.",
        )
    if request.headers.get("x-seller-request") != "1":
        raise HTTPException(
            status_code=403,
            detail="The seller request validation header is required.",
        )


def _seller_product_payload(
    product: SellerProductInput,
    seller: sqlite3.Row,
    product_id: str,
) -> dict:
    images = product.images
    is_agri_product = (
        seller["business_type"] == AGRICULTURE_BUSINESS_TYPE
        or product.category in AGRICULTURE_PRODUCT_CATEGORIES
    )
    return {
        "id": product_id,
        "name": product.name,
        "brand": product.brand,
        "sku": product.sku.upper(),
        "category": product.category,
        "detail": product.detail,
        "description": product.description,
        "price": product.price,
        "stock": product.stock,
        "low_stock_threshold": product.lowStockThreshold,
        "image": images[0],
        "gallery_json": json.dumps(images),
        "tags_json": json.dumps(product.tags),
        "variants_json": json.dumps(
            [variant.model_dump() for variant in product.variants]
        ),
        "product_status": product.status,
        "active": int(product.status == "ACTIVE"),
        "seller_id": seller["id"],
        "is_agri_product": int(is_agri_product),
        "farmer_name": seller["owner_name"] or seller["store_name"] if is_agri_product else "",
        "farmer_whatsapp": seller["whatsapp_number"] or seller["whatsapp_phone"] if is_agri_product else "",
        "seller_whatsapp_phone": seller["whatsapp_number"] or seller["whatsapp_phone"],
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_seller(application: SellerRegistration, request: Request, response: Response) -> dict:
    _verify_seller_write(request)
    slug_base = re.sub(r"[^a-z0-9]+", "-", application.store_name.casefold()).strip("-")
    seller_status = (
        "APPROVED" if auto_approve_seller_registrations_enabled() else "PENDING"
    )
    with get_connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO users (
                    full_name, email, password_hash, role, phone,
                    business_type, whatsapp_number
                ) VALUES (?, ?, ?, 'seller', ?, ?, ?)
                """,
                (
                    application.owner_name,
                    application.email,
                    _password_hash(application.password),
                    application.business_phone,
                    application.business_type,
                    application.whatsapp_number,
                ),
            )
            user_id = cursor.lastrowid
            store_slug = slug_base or f"store-{user_id}"
            if connection.execute(
                "SELECT 1 FROM sellers WHERE store_slug = ?", (store_slug,)
            ).fetchone():
                store_slug = f"{store_slug}-{user_id}"
            cursor = connection.execute(
                """
                INSERT INTO sellers (
                    user_id, store_name, store_slug, logo_url, banner_url,
                    business_phone, payout_method, payout_account,
                    owner_name, submitted_documents_json, business_category,
                    business_type, whatsapp_phone, whatsapp_number, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    application.store_name,
                    store_slug,
                    application.logo_url,
                    application.banner_url,
                    application.business_phone,
                    application.payout_method,
                    application.payout_account,
                    application.owner_name,
                    json.dumps(application.submitted_documents),
                    application.business_category,
                    application.business_type,
                    application.whatsapp_number,
                    application.whatsapp_number,
                    seller_status,
                ),
            )
            connection.execute(
                """
                INSERT INTO seller_profiles (
                    user_id, seller_id, store_name, store_slug, business_phone,
                    payout_number, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    cursor.lastrowid,
                    application.store_name,
                    store_slug,
                    application.business_phone,
                    application.payout_account,
                    seller_status.casefold(),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="An account already uses this email address.",
            ) from error
        seller = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    _set_seller_session(user_id, response)
    return _seller_payload(seller, include_payout=True)


@router.post("/login")
def login_seller(credentials: SellerLogin, request: Request, response: Response) -> dict:
    _verify_seller_write(request)
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
            "SELECT id, password_hash FROM users WHERE email = ? AND role = 'seller'",
            (credentials.email,),
        ).fetchone()
        valid = user is not None and _password_matches(
            credentials.password, user["password_hash"]
        )
        if valid:
            connection.execute(
                """
                INSERT INTO user_login_events (user_id, provider, created_at)
                VALUES (?, 'seller-password', ?)
                """,
                (user["id"], now.isoformat()),
            )
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
    _set_seller_session(user["id"], response)
    return {"signed_in": True}


@router.post("/logout")
def logout_seller(request: Request, response: Response) -> dict:
    _verify_seller_write(request)
    raw_token = request.cookies.get(SELLER_COOKIE_NAME, "")
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with get_connection() as connection:
            connection.execute(
                "UPDATE seller_sessions SET revoked_at = ? WHERE token_hash = ?",
                (datetime.now(timezone.utc).isoformat(), token_hash),
            )
            connection.commit()
    response.delete_cookie(SELLER_COOKIE_NAME, path="/", samesite="lax")
    return {"signed_out": True}


@router.get("/me")
def seller_me(request: Request) -> dict:
    seller = require_seller(request, allow_suspended=True)
    return _seller_payload(seller, include_payout=True)


@router.put("/approve-self")
def approve_seller_self(request: Request) -> dict:
    _verify_seller_write(request)
    if not demo_seller_approval_enabled():
        raise HTTPException(
            status_code=404, detail="Seller self-approval is not available."
        )
    seller = require_seller(request)
    if seller["review_state"] == "UNDER_AUDIT":
        raise HTTPException(
            status_code=409, detail="A seller under audit cannot be self-approved."
        )
    if seller["status"] == "SUSPENDED":
        raise HTTPException(
            status_code=409, detail="A suspended seller cannot be self-approved."
        )
    with get_connection() as connection:
        connection.execute(
            "UPDATE sellers SET status = 'APPROVED' WHERE id = ?",
            (seller["id"],),
        )
        connection.execute(
            "UPDATE seller_profiles SET status = 'approved' WHERE seller_id = ?",
            (seller["id"],),
        )
        connection.commit()
        updated = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (seller["id"],),
        ).fetchone()
    return _seller_payload(updated, include_payout=True)


@router.post("/approve-all")
def approve_all_sellers(request: Request) -> dict:
    _verify_seller_write(request)
    if not demo_seller_approval_enabled():
        raise HTTPException(
            status_code=404, detail="Bulk seller approval is not available."
        )
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE sellers SET status = 'APPROVED'
            WHERE status = 'PENDING' AND review_state = 'CLEAR'
            """
        )
        approved_count = cursor.rowcount
        connection.execute(
            """
            UPDATE seller_profiles SET status = 'approved'
            WHERE seller_id IN (
                SELECT id FROM sellers
                WHERE status = 'APPROVED' AND review_state = 'CLEAR'
            )
            """
        )
        connection.commit()
    return {"approved_count": approved_count}


@router.get("/stores/{store_slug}")
def public_store(store_slug: str) -> dict:
    with get_connection() as connection:
        expire_seller_promotions(connection)
        seller = connection.execute(
            """
            SELECT id, store_name, store_slug, store_bio, business_category,
                   logo_url, banner_url, rating, business_phone, whatsapp_phone,
                   instagram_url, tiktok_url, operating_hours, holiday_mode
            FROM sellers
            WHERE store_slug = ? AND status = 'APPROVED' AND review_state = 'CLEAR'
              AND maintenance_mode = 0
            """,
            (store_slug,),
        ).fetchone()
        if seller is None:
            raise HTTPException(status_code=404, detail="Store not found.")
        products = connection.execute(
            """
            SELECT p.*, s.store_name AS linked_seller_name,
                   s.store_slug AS linked_seller_slug,
                   s.rating AS seller_rating, s.logo_url AS seller_logo,
                   s.business_phone AS linked_seller_phone,
                   s.whatsapp_phone AS linked_seller_whatsapp_phone,
                   s.whatsapp_number AS linked_farmer_whatsapp_number,
                   s.business_type AS linked_business_type,
                   1 AS linked_seller_verified, s.holiday_mode AS seller_holiday_mode
            FROM products p JOIN sellers s ON s.id = p.seller_id
            WHERE p.seller_id = ? AND p.active = 1
              AND p.product_status = 'ACTIVE'
              AND s.status = 'APPROVED' AND s.review_state = 'CLEAR'
              AND s.maintenance_mode = 0
            ORDER BY p.name
            """,
            (seller["id"],),
        ).fetchall()
    store_info = dict(seller)
    store_info["seller_phone"] = store_info["business_phone"]
    store_info["seller_verified"] = True
    store_info["whatsapp_phone"] = (
        store_info["whatsapp_phone"] or store_info["business_phone"]
    )
    return {
        "store": store_info,
        "products": [serialize_product(product) for product in products],
    }


@router.get("/dashboard")
def seller_dashboard(
    request: Request,
    period: str = Query(default="30d", pattern="^(7d|30d|ytd)$"),
) -> dict:
    seller = require_seller(request)
    today = date.today()
    start_date = (
        date(today.year, 1, 1)
        if period == "ytd"
        else today - timedelta(days=6 if period == "7d" else 29)
    )
    with get_connection() as connection:
        products = connection.execute(
            """
            SELECT COUNT(*) AS product_count,
                   SUM(CASE WHEN stock <= low_stock_threshold THEN 1 ELSE 0 END) AS low_stock
            FROM products WHERE seller_id = ? AND active = 1
            """,
            (seller["id"],),
        ).fetchone()
        orders = connection.execute(
            """
            SELECT so.items_json, so.subtotal, so.seller_payout_amount, so.fulfillment_status,
                   o.payment_status
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ?
            """,
            (seller["id"],),
        ).fetchall()
        paid_orders = [
            row for row in orders
            if row["payment_status"] in {"paid", "completed_demo"}
        ]
        item_count = sum(
            sum(item["quantity"] for item in json.loads(row["items_json"]))
            for row in paid_orders
        )
        paid_earnings = sum(
            row["seller_payout_amount"]
            for row in orders
            if row["payment_status"] in {"paid", "completed_demo"}
        )
        gross_sales = sum(
            row["subtotal"]
            for row in orders
            if row["payment_status"] in {"paid", "completed_demo"}
        )
        available_balance = connection.execute(
            """
            SELECT COALESCE(SUM(
                COALESCE(ledger.net_amount, so.seller_payout_amount)
                - COALESCE(ledger.paid_amount, 0)
            ), 0)
            FROM sub_orders so
            JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN payout_allocations pa ON pa.sub_order_id = so.id
            LEFT JOIN seller_payout_ledger ledger ON ledger.sub_order_id = so.id
            WHERE so.seller_id = ? AND o.payment_status IN ('paid', 'completed_demo')
              AND so.fulfillment_status = 'DELIVERED'
              AND pa.sub_order_id IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM seller_payout_ledger paid_ledger
                  WHERE paid_ledger.sub_order_id = so.id
                    AND paid_ledger.status = 'PAID (DEMO)'
                    AND paid_ledger.paid_amount >= paid_ledger.net_amount
              )
            """,
            (seller["id"],),
        ).fetchone()[0]
        ad_spend = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM seller_ad_transactions
            WHERE seller_id = ? AND status = 'COMPLETED'
            """,
            (seller["id"],),
        ).fetchone()[0]
        available_balance = max(0, available_balance - ad_spend)
        period_orders = connection.execute(
            """
            SELECT substr(o.created_at, 1, 10) AS sales_date,
                   SUM(so.subtotal) AS gross,
                   SUM(so.commission_amount) AS commission,
                   SUM(so.seller_payout_amount) AS net
            FROM sub_orders so
            JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ?
              AND o.payment_status IN ('paid', 'completed_demo')
              AND substr(o.created_at, 1, 10) >= ?
              AND substr(o.created_at, 1, 10) <= ?
            GROUP BY substr(o.created_at, 1, 10)
            ORDER BY sales_date
            """,
            (seller["id"], start_date.isoformat(), today.isoformat()),
        ).fetchall()
    daily_totals = {
        row["sales_date"]: {
            "gross": round(row["gross"] or 0, 2),
            "commission": round(row["commission"] or 0, 2),
            "net": round(row["net"] or 0, 2),
        }
        for row in period_orders
    }
    sales_series = []
    current_day = start_date
    while current_day <= today:
        day = current_day.isoformat()
        sales_series.append(
            {"date": day, **daily_totals.get(day, {"gross": 0, "commission": 0, "net": 0})}
        )
        current_day += timedelta(days=1)
    return {
        "status": seller["status"],
        "gross_sales": round(gross_sales, 2),
        "net_earnings": round(paid_earnings, 2),
        "total_items_sold": item_count,
        "pending_orders": sum(
            row["fulfillment_status"] != "DELIVERED" for row in orders
        ),
        "low_stock_alerts": products["low_stock"] or 0,
        "product_count": products["product_count"] or 0,
        "average_rating": seller["rating"],
        "selected_plan": seller["selected_plan"] or "boutique",
        "commission_rate": seller["commission_rate"],
        "available_balance": round(available_balance, 2),
        "analytics_period": period,
        "sales_series": sales_series,
    }


@router.put("/profile")
def update_seller_profile(
    update: SellerStorefrontUpdate, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    if re.sub(r"\D", "", update.business_phone) != re.sub(
        r"\D", "", seller["business_phone"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Phone changes require email verification. Use the profile verification flow.",
        )
    if update.email and update.email.casefold() != seller["email"].casefold():
        raise HTTPException(
            status_code=409,
            detail="Email changes require verification. Use the profile verification flow.",
        )
    if (
        update.payout_method == "M-Pesa"
        and re.sub(r"\D", "", update.payout_account)
        != re.sub(r"\D", "", update.business_phone)
    ):
        raise HTTPException(
            status_code=409,
            detail="The registered M-Pesa payout line must match the verified business phone.",
        )
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE sellers
            SET store_name = ?, store_bio = ?, business_category = ?,
                logo_url = ?, banner_url = ?, business_phone = ?,
                whatsapp_phone = ?, instagram_url = ?, tiktok_url = ?,
                operating_hours = ?, holiday_mode = ?,
                payout_method = ?, payout_account = ?
            WHERE id = ?
            """,
            (
                update.store_name,
                update.store_bio,
                update.business_category,
                update.logo_url,
                update.banner_url,
                update.business_phone,
                update.whatsapp_phone,
                update.instagram_url,
                update.tiktok_url,
                update.operating_hours,
                int(update.holiday_mode),
                update.payout_method,
                update.payout_account,
                seller["id"],
            ),
        )
        connection.execute(
            """
            UPDATE seller_profiles
            SET store_name = ?, business_category = ?, business_phone = ?,
                payout_number = ?
            WHERE seller_id = ?
            """,
            (
                update.store_name,
                update.business_category,
                update.business_phone,
                update.payout_account,
                seller["id"],
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (seller["id"],),
        ).fetchone()
    return _seller_payload(row, include_payout=True)


@router.post("/request-profile-update", status_code=status.HTTP_202_ACCEPTED)
def request_profile_update(
    update: SellerProfileUpdateRequest, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    new_email = update.new_email or seller["email"]
    new_phone = update.new_phone or seller["business_phone"]
    changed_email = new_email.casefold() != seller["email"].casefold()
    changed_phone = re.sub(r"\D", "", new_phone) != re.sub(
        r"\D", "", seller["business_phone"]
    )
    if not changed_email and not changed_phone:
        raise HTTPException(
            status_code=400, detail="No email or phone changes were submitted."
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)
    code_hash = hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if changed_email:
            existing = connection.execute(
                "SELECT id FROM users WHERE email = ? COLLATE NOCASE AND id != ?",
                (new_email, seller["user_id"]),
            ).fetchone()
            if existing:
                raise HTTPException(
                    status_code=409, detail="That email is already in use."
                )
        recent_requests = connection.execute(
            """
            SELECT COUNT(*) FROM seller_profile_update_tokens
            WHERE seller_id = ? AND created_at >= ?
            """,
            (
                seller["id"],
                (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            ),
        ).fetchone()[0]
        if recent_requests >= 5:
            raise HTTPException(
                status_code=429,
                detail="Too many verification requests. Try again in an hour.",
            )
        connection.execute(
            """
            UPDATE seller_profile_update_tokens SET used_at = ?
            WHERE seller_id = ? AND used_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(), seller["id"]),
        )
        connection.execute(
            """
            INSERT INTO seller_profile_update_tokens (
                seller_id, new_email, new_phone, code_salt, code_hash, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (seller["id"], new_email, new_phone, salt, code_hash, expires_at),
        )
        connection.commit()

    recipient = new_email if changed_email else seller["email"]
    _deliver_seller_update_code(recipient, code, changed_email, changed_phone)
    return {
        "message": f"Confirmation code sent to {recipient}.",
        "delivery_address": recipient,
        "expires_in_seconds": 600,
    }


@router.post("/verify-profile-update")
def verify_profile_update(
    update: SellerProfileUpdateVerify, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        pending = connection.execute(
            """
            SELECT * FROM seller_profile_update_tokens
            WHERE seller_id = ? AND used_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (seller["id"],),
        ).fetchone()
        if pending is None:
            raise HTTPException(
                status_code=400, detail="Request a new profile verification code."
            )
        if pending["expires_at"] <= now:
            connection.execute(
                "UPDATE seller_profile_update_tokens SET used_at = ? WHERE id = ?",
                (now, pending["id"]),
            )
            connection.commit()
            raise HTTPException(
                status_code=400, detail="The confirmation code expired. Request a new one."
            )
        if pending["attempts"] >= 5:
            connection.execute(
                "UPDATE seller_profile_update_tokens SET used_at = ? WHERE id = ?",
                (now, pending["id"]),
            )
            connection.commit()
            raise HTTPException(
                status_code=429, detail="Too many incorrect codes. Request a new code."
            )
        supplied_hash = hashlib.sha256(
            f"{pending['code_salt']}:{update.code}".encode("utf-8")
        ).hexdigest()
        if not secrets.compare_digest(supplied_hash, pending["code_hash"]):
            connection.execute(
                "UPDATE seller_profile_update_tokens SET attempts = attempts + 1 WHERE id = ?",
                (pending["id"],),
            )
            connection.commit()
            raise HTTPException(status_code=400, detail="That confirmation code is incorrect.")
        try:
            connection.execute(
                "UPDATE users SET email = ?, phone = ? WHERE id = ?",
                (pending["new_email"], pending["new_phone"], seller["user_id"]),
            )
            connection.execute(
                """
                UPDATE sellers
                SET business_phone = ?,
                    payout_account = CASE
                        WHEN payout_method = 'M-Pesa' THEN ? ELSE payout_account
                    END
                WHERE id = ?
                """,
                (pending["new_phone"], pending["new_phone"], seller["id"]),
            )
            connection.execute(
                """
                UPDATE seller_profiles
                SET business_phone = ?,
                    payout_number = CASE
                        WHEN (SELECT payout_method FROM sellers WHERE id = ?) = 'M-Pesa'
                        THEN ? ELSE payout_number
                    END
                WHERE seller_id = ?
                """,
                (
                    pending["new_phone"],
                    seller["id"],
                    pending["new_phone"],
                    seller["id"],
                ),
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise HTTPException(
                status_code=409, detail="That email is already in use."
            ) from error
        connection.execute(
            "UPDATE seller_profile_update_tokens SET used_at = ? WHERE id = ?",
            (now, pending["id"]),
        )
        connection.commit()
        profile = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (seller["id"],),
        ).fetchone()
    return {
        "message": "Seller contact details updated.",
        "seller": _seller_payload(profile, include_payout=True),
    }


@router.put("/plan")
def update_seller_plan(update: SellerPlanUpdate, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    commission_rate = PLAN_RATES[update.selected_plan]
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE sellers
            SET selected_plan = ?, commission_rate = ?,
                commission_percentage = ?, commission_is_custom = 0
            WHERE id = ?
            """,
            (
                update.selected_plan,
                commission_rate,
                commission_rate,
                seller["id"],
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (seller["id"],),
        ).fetchone()
    return _seller_payload(row, include_payout=True)


@router.post("/upgrade-plan")
def upgrade_seller_plan(update: SellerPlanUpgrade, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    reference = f"DEMO-STK-{secrets.token_hex(5).upper()}"
    amount = PLAN_PRICES[update.selected_plan]
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO seller_subscription_transactions (
                seller_id, selected_plan, amount, reference, status
            ) VALUES (?, ?, ?, ?, 'COMPLETED')
            """,
            (seller["id"], update.selected_plan, amount, reference),
        )
        connection.execute(
            """
            UPDATE sellers
            SET selected_plan = ?, commission_rate = ?,
                commission_percentage = ?, commission_is_custom = 0
            WHERE id = ?
            """,
            (
                update.selected_plan,
                PLAN_RATES[update.selected_plan],
                PLAN_RATES[update.selected_plan],
                seller["id"],
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT s.*, u.email FROM sellers s JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (seller["id"],),
        ).fetchone()
    return {
        "seller": _seller_payload(row, include_payout=True),
        "subscription": {
            "plan": update.selected_plan,
            "amount": amount,
            "currency": "KES",
            "payment_method": "M-Pesa STK Push (SIMULATED)",
            "reference": reference,
            "status": "COMPLETED",
            "is_simulated": True,
        },
    }


@router.get("/payouts")
def seller_payouts(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, amount, commission_retained, payout_method, reference,
                   status, transaction_id, destination_type, destination_hint,
                   created_at, paid_by
            FROM payout_transactions
            WHERE seller_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (seller["id"],),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "date": row["created_at"],
            "reference": row["reference"],
            "transaction_id": row["transaction_id"],
            "gross_amount": round(row["amount"] + row["commission_retained"], 2),
            "net_paid": row["amount"],
            "commission_retained": row["commission_retained"],
            "payout_method": row["payout_method"],
            "destination_type": row["destination_type"],
            "destination_hint": row["destination_hint"],
            "status": row["status"],
            "is_demo": row["paid_by"] == "seller_demo",
        }
        for row in rows
    ]


@router.post("/withdraw", status_code=status.HTTP_201_CREATED)
def simulate_seller_withdrawal(
    request: Request, payout: SellerWithdrawalInput | None = None
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    if seller["payout_method"] != "M-Pesa":
        raise HTTPException(
            status_code=409,
            detail="Switch your payout method to M-Pesa before requesting this demo payout.",
        )
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT OR IGNORE INTO seller_payout_ledger (
                seller_id, sub_order_id, gross_amount, commission_amount, net_amount,
                status, transaction_reference
            )
            SELECT so.seller_id, so.id, so.subtotal, so.commission_amount,
                   so.seller_payout_amount, 'ESCROW PAID (DEMO)',
                   COALESCE(NULLIF(o.gateway_reference, ''), o.gateway_tracking_id, '')
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ? AND o.payment_status IN ('paid', 'completed_demo')
            """,
            (seller["id"],),
        )
        eligible = connection.execute(
            """
            SELECT ledger.id AS ledger_id, so.id AS sub_order_id,
                   ledger.gross_amount, ledger.commission_amount, ledger.net_amount,
                   ledger.net_amount - ledger.paid_amount AS remaining_amount
            FROM seller_payout_ledger ledger
            JOIN sub_orders so ON so.id = ledger.sub_order_id
            JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ? AND o.payment_status IN ('paid', 'completed_demo')
              AND so.fulfillment_status = 'DELIVERED'
              AND ledger.status IN ('ESCROW PAID (DEMO)', 'PARTIALLY PAID (DEMO)')
              AND ledger.paid_amount < ledger.net_amount
            ORDER BY ledger.id
            """,
            (seller["id"],),
        ).fetchall()
        available_amount = round(
            sum(row["remaining_amount"] for row in eligible), 2
        )
        ad_spend = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM seller_ad_transactions
            WHERE seller_id = ? AND status = 'COMPLETED'
            """,
            (seller["id"],),
        ).fetchone()[0]
        available_amount = round(max(0, available_amount - ad_spend), 2)
        requested_amount = (
            round(payout.amount, 2) if payout else available_amount
        )
        if requested_amount < 1 or requested_amount > available_amount:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Demo payouts must be at least KSh 1 and cannot exceed your "
                    f"available balance of KSh {available_amount:,.2f}."
                ),
            )
        destination_type = payout.destination_type if payout else "registered_phone"
        destination = (
            seller["payout_account"]
            if destination_type == "registered_phone"
            else payout.destination
        )
        if destination_type == "registered_phone" and not destination:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="Add a registered M-Pesa payout number in boutique settings.",
            )
        reference_suffix = secrets.token_hex(5).upper()
        reference = f"DEMO-MPESA-{reference_suffix}"
        transaction_id = f"SIMULATED-{reference_suffix}"
        remaining_to_allocate = requested_amount
        commission_retained = 0.0
        allocations = []
        for row in eligible:
            if remaining_to_allocate <= 0:
                break
            allocated = min(row["remaining_amount"], remaining_to_allocate)
            commission_retained += (
                row["commission_amount"] * allocated / row["net_amount"]
                if row["net_amount"] > 0 else 0
            )
            allocations.append((row, round(allocated, 2)))
            remaining_to_allocate = round(remaining_to_allocate - allocated, 2)
        commission_retained = round(commission_retained, 2)
        destination_hint = f"••••{destination[-4:]}"
        cursor = connection.execute(
            """
            INSERT INTO payout_transactions (
                seller_id, amount, commission_retained, payout_method,
                reference, status, transaction_id, destination_type,
                destination_hint, paid_by
            ) VALUES (?, ?, ?, 'M-Pesa', ?, 'COMPLETED', ?, ?, ?, 'seller_demo')
            """,
            (
                seller["id"],
                requested_amount,
                commission_retained,
                reference,
                transaction_id,
                destination_type,
                destination_hint,
            ),
        )
        for row, allocated in allocations:
            connection.execute(
                """
                INSERT INTO seller_demo_payout_allocations (
                    payout_transaction_id, ledger_id, amount
                ) VALUES (?, ?, ?)
                """,
                (cursor.lastrowid, row["ledger_id"], allocated),
            )
            connection.execute(
                """
                UPDATE seller_payout_ledger
                SET paid_amount = paid_amount + ?,
                    status = CASE
                        WHEN paid_amount + ? >= net_amount THEN 'PAID (DEMO)'
                        ELSE 'PARTIALLY PAID (DEMO)'
                    END,
                    payout_reference = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (allocated, allocated, reference, row["ledger_id"]),
            )
            if allocated >= row["remaining_amount"]:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO payout_allocations (
                        payout_transaction_id, sub_order_id
                    ) VALUES (?, ?)
                    """,
                    (cursor.lastrowid, row["sub_order_id"]),
                )
        connection.commit()
    return {
        "id": cursor.lastrowid,
        "reference": reference,
        "transaction_id": transaction_id,
        "amount": requested_amount,
        "payout_method": "M-Pesa",
        "destination_type": destination_type,
        "destination_hint": destination_hint,
        "status": "COMPLETED",
        "is_demo": True,
        "message": "Simulated payout recorded; no M-Pesa transfer was sent.",
    }


@router.get("/products")
def seller_products(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        expire_seller_promotions(connection)
        rows = connection.execute(
            """
            SELECT * FROM products
            WHERE seller_id = ? ORDER BY name
            """,
            (seller["id"],),
        ).fetchall()
    return [serialize_product(row) for row in rows]


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_seller_image(
    request: Request, image: UploadFile = File(...)
) -> dict:
    _verify_seller_write(request)
    require_seller(request, approved=True)
    content_types = {
        "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
        "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
        "image/webp": (
            ".webp",
            lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        ),
    }
    image_type = content_types.get(image.content_type or "")
    if image_type is None:
        raise HTTPException(
            status_code=415, detail="Upload a JPEG, PNG, or WebP image."
        )
    contents = await image.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    extension, matches_signature = image_type
    if not matches_signature(contents):
        raise HTTPException(
            status_code=415, detail="The uploaded file does not match its image type."
        )
    file_name = f"{secrets.token_hex(16)}{extension}"
    try:
        (UPLOAD_ROOT / file_name).write_bytes(contents)
    except OSError as error:
        raise HTTPException(
            status_code=500, detail="The image could not be saved."
        ) from error
    finally:
        await image.close()
    return {
        "url": f"{str(request.base_url).rstrip('/')}/uploads/{file_name}",
        "content_type": image.content_type,
    }


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_seller_product(product: SellerProductInput, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    values = _seller_product_payload(product, seller, str(uuid.uuid4()))
    values.update(
        product_status="DRAFT",
        active=0,
        qc_status="PENDING_QC",
    )
    with get_connection() as connection:
        try:
            connection.execute(
                """
                INSERT INTO products (
                    id, name, brand, sku, category, detail, description, price,
                    stock, low_stock_threshold, image, gallery_json, seller_id,
                    tags_json, variants_json, product_status, active, qc_status,
                    is_agri_product, farmer_name, farmer_whatsapp,
                    seller_whatsapp_phone
                ) VALUES (
                    :id, :name, :brand, :sku, :category, :detail, :description, :price,
                    :stock, :low_stock_threshold, :image, :gallery_json, :seller_id,
                    :tags_json, :variants_json, :product_status, :active, :qc_status,
                    :is_agri_product, :farmer_name, :farmer_whatsapp,
                    :seller_whatsapp_phone
                )
                """,
                values,
            )
            connection.execute(
                """INSERT INTO seller_qc_audits
                   (seller_id, product_id, qc_status, notes, reviewed_by)
                   VALUES (?, ?, 'PENDING_QC', 'New listing submitted for review.', 'seller')""",
                (seller["id"], values["id"]),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="That SKU is already in use.") from error
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (values["id"],)
        ).fetchone()
    return serialize_product(row)


@router.put("/products/{product_id}")
def update_seller_product(
    product_id: str, product: SellerProductInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    values = _seller_product_payload(product, seller, product_id)
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT qc_status FROM products WHERE id = ? AND seller_id = ?",
            (product_id, seller["id"]),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Your product was not found.")
        if values["product_status"] == "ACTIVE" and existing["qc_status"] != "APPROVED_LIVE":
            values["product_status"] = "DRAFT"
            values["active"] = 0
        try:
            cursor = connection.execute(
                """
                UPDATE products SET
                    name = :name, brand = :brand, sku = :sku, category = :category,
                    detail = :detail, description = :description, price = :price,
                    stock = :stock, low_stock_threshold = :low_stock_threshold,
                    image = :image, gallery_json = :gallery_json,
                    tags_json = :tags_json, variants_json = :variants_json,
                    product_status = :product_status, active = :active,
                    is_agri_product = :is_agri_product,
                    farmer_name = :farmer_name,
                    farmer_whatsapp = :farmer_whatsapp,
                    seller_whatsapp_phone = :seller_whatsapp_phone
                WHERE id = :id AND seller_id = :seller_id
                """,
                values,
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="That SKU is already in use.") from error
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Your product was not found.")
        connection.commit()
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    return serialize_product(row)


@router.post("/products/bulk")
def bulk_update_seller_products(
    update: SellerProductBulkInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    placeholders = ",".join("?" for _ in update.product_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id FROM products
            WHERE seller_id = ? AND id IN ({placeholders})
            """,
            [seller["id"], *update.product_ids],
        ).fetchall()
        if len(rows) != len(update.product_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more selected products could not be found.",
            )
        if update.action == "status":
            if update.status == "ACTIVE":
                pending_qc = connection.execute(
                    f"""SELECT COUNT(*) FROM products
                        WHERE seller_id = ? AND id IN ({placeholders})
                          AND qc_status != 'APPROVED_LIVE'""",
                    [seller["id"], *update.product_ids],
                ).fetchone()[0]
                if pending_qc:
                    raise HTTPException(
                        status_code=409,
                        detail="Products must pass quality control before they can be activated.",
                    )
            connection.execute(
                f"""
                UPDATE products SET product_status = ?, active = ?
                WHERE seller_id = ? AND id IN ({placeholders})
                """,
                [
                    update.status,
                    int(update.status == "ACTIVE"),
                    seller["id"],
                    *update.product_ids,
                ],
            )
        elif update.action == "out_of_stock":
            connection.execute(
                f"""
                UPDATE products SET stock = 0
                WHERE seller_id = ? AND id IN ({placeholders})
                """,
                [seller["id"], *update.product_ids],
            )
        else:
            percentage = update.discount_percent
            connection.execute(
                f"""
                UPDATE products
                SET old_price = price,
                    price = ROUND(price * (1 - ? / 100.0), 2),
                    discount = ? || '% OFF'
                WHERE seller_id = ? AND id IN ({placeholders})
                """,
                [percentage, percentage, seller["id"], *update.product_ids],
            )
        connection.commit()
        changed = connection.execute(
            f"""
            SELECT * FROM products
            WHERE seller_id = ? AND id IN ({placeholders})
            ORDER BY name
            """,
            [seller["id"], *update.product_ids],
        ).fetchall()
    return {"products": [serialize_product(row) for row in changed]}


@router.delete("/products/{product_id}")
def delete_seller_product(product_id: str, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE products SET active = 0 WHERE id = ? AND seller_id = ?",
            (product_id, seller["id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Your product was not found.")
        connection.commit()
    return {"deleted": True}


@router.get("/orders")
def seller_orders(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT so.*, o.order_number, o.customer_name, o.customer_phone,
                   o.tracking_id, o.delivery_address, o.payment_status,
                   o.created_at AS ordered_at,
                   ledger.status AS payout_status,
                   ledger.transaction_reference AS payment_reference
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN seller_payout_ledger ledger ON ledger.sub_order_id = so.id
            WHERE so.seller_id = ? ORDER BY o.created_at DESC
            """,
            (seller["id"],),
        ).fetchall()
        timelines = {
            row["id"]: status_timeline(connection, row["id"])
            for row in rows
        }
    return [
        {
            "id": row["id"],
            "order_number": row["order_number"],
            "customer": {
                "name": row["customer_name"],
                "phone": row["customer_phone"],
                "address": row["delivery_address"],
            },
            "items": json.loads(row["items_json"]),
            "subtotal": row["subtotal"],
            "commission_amount": row["commission_amount"],
            "seller_payout_amount": row["seller_payout_amount"],
            "fulfillment_status": row["fulfillment_status"],
            "tracking_status": effective_fulfillment_status(row),
            "payment_status": row["payment_status"],
            "payout_status": row["payout_status"],
            "payment_reference": row["payment_reference"],
            "courier_name": row["courier_name"],
            "tracking_number": row["tracking_number"],
            "tracking_id": row["tracking_id"],
            "ordered_at": row["ordered_at"],
            "updated_at": row["updated_at"],
            "timeline": timelines[row["id"]],
        }
        for row in rows
    ]


def _update_seller_order_fulfillment(
    sub_order_id: int,
    update: SellerFulfillmentUpdate,
    request: Request,
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        target_status, parent_order_id = apply_seller_fulfillment(
            connection,
            sub_order_id,
            seller["id"],
            update.status,
            update.courier_name,
            update.tracking_number,
        )
        connection.commit()
    display_status = {
        "PENDING": "PENDING_PACKING",
        "PROCESSING": "PACKED",
        "SHIPPED": "DISPATCHED_TO_COURIER",
        "DELIVERED": "DELIVERED",
    }[target_status]
    publish_order_update(request, parent_order_id, sub_order_id, display_status)
    return {
        "id": sub_order_id,
        "fulfillment_status": target_status,
        "pipeline_status": update.status,
        "courier_name": update.courier_name,
        "tracking_number": update.tracking_number,
    }


@router.put("/orders/{sub_order_id}/status")
def update_seller_order_status(
    sub_order_id: int, update: SellerFulfillmentUpdate, request: Request
) -> dict:
    return _update_seller_order_fulfillment(sub_order_id, update, request)


@router.patch("/orders/{sub_order_id}")
def update_seller_order(
    sub_order_id: int, update: SellerFulfillmentUpdate, request: Request
) -> dict:
    return _update_seller_order_fulfillment(sub_order_id, update, request)
