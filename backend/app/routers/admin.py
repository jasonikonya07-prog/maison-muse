import csv
import io
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.admin_auth import (
    ADMIN_COOKIE_NAME,
    current_admin,
    current_admin_details,
    login_admin,
    logout_admin,
    require_admin,
)
from app.database import get_connection
from app.order_tracking import (
    decoded_items,
    effective_fulfillment_status,
    publish_order_update,
    record_order_status_event,
    status_timeline,
)
from app.pesapal import is_configured, refresh_order_payment
from app.routers.products import serialize_product
from app.schemas import (
    AdminLogin,
    AdminOrderOverrideUpdate,
    CampaignInput,
    CommissionSettingsUpdate,
    MarketplaceDisputeInput,
    MarketplacePayoutUpdate,
    OrderStatusUpdate,
    ProductAdminInput,
    ProductCostUpdate,
    PurchaseOrderInput,
    RolePermissionsUpdate,
    SellerPayoutInput,
    SellerQcReviewUpdate,
    SellerReviewUpdate,
    SellerStatusUpdate,
    StoreSettingsUpdate,
)


router = APIRouter()
ORDER_STATUSES = ("pending", "processing", "shipped", "delivered", "cancelled")
PRODUCT_CATEGORIES = (
    "Perfumes & Fragrances",
    "Press-On Nails",
    "Skincare & Glow",
    "Lip & Makeup Essentials",
    "Hair & Accessories",
)


def _admin(request: Request) -> str:
    return require_admin(request)


def _role_permissions(role: str) -> dict:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT permissions_json FROM admin_role_permissions WHERE role = ?",
            (role,),
        ).fetchone()
    return json.loads(row["permissions_json"]) if row else {}


def _authorize(request: Request, area: str, right: str) -> str:
    username = _admin(request)
    identity = request.state.admin_identity
    permissions = _role_permissions(identity["role"])
    if not permissions.get(area, {}).get(right, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your {identity['role']} role does not have {right} access to {area}.",
        )
    return username


def _audit(
    connection: sqlite3.Connection,
    request: Request,
    category: str,
    event_type: str,
    description: str,
    severity: str = "INFO",
    details: dict | None = None,
) -> None:
    identity = getattr(request.state, "admin_identity", {})
    connection.execute(
        """
        INSERT INTO admin_audit_logs (
            occurred_at, admin_username, event_category, event_type,
            description, ip_address, severity, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            identity.get("username", "Unknown"),
            category,
            event_type,
            description[:1000],
            request.client.host if request.client else "unknown",
            severity,
            json.dumps(details or {}),
        ),
    )


def _audit_rows(connection: sqlite3.Connection, query: str, parameters: tuple) -> list[dict]:
    rows = connection.execute(query, parameters).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        result.append(item)
    return result


def _verify_admin_write(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in request.app.state.cors_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin requests must come from an approved storefront origin.",
        )
    if request.headers.get("x-admin-request") != "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The admin request validation header is required.",
        )


@router.get("/marketplace")
def marketplace_management(request: Request) -> dict:
    _authorize(request, "settings", "write")
    with get_connection() as connection:
        vendors = connection.execute(
            """
            SELECT s.id, s.store_name, s.store_slug, s.logo_url, s.banner_url,
                   s.owner_name, s.submitted_documents_json, s.review_note,
                   s.review_state, s.business_phone, s.payout_method,
                   s.payout_account, s.business_category,
                   s.business_registration_number, s.status, s.rating, s.commission_percentage,
                   s.commission_is_custom,
                   u.email,
                   (SELECT COUNT(*) FROM products p
                    WHERE p.seller_id = s.id AND p.active = 1) AS live_product_count,
                   COALESCE((
                       SELECT AVG(p.rating) FROM products p
                       WHERE p.seller_id = s.id AND p.active = 1 AND p.rating IS NOT NULL
                   ), s.rating) AS rating_average,
                   COALESCE((
                       SELECT SUM(so.subtotal) FROM sub_orders so
                       JOIN orders o ON o.id = so.parent_order_id
                       WHERE so.seller_id = s.id AND o.payment_status = 'paid'
                   ), 0) AS store_revenue,
                   COALESCE((
                       SELECT SUM(so.seller_payout_amount)
                       FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
                       LEFT JOIN payout_allocations pa ON pa.sub_order_id = so.id
                       WHERE so.seller_id = s.id AND o.payment_status = 'paid'
                         AND so.fulfillment_status = 'DELIVERED'
                         AND pa.sub_order_id IS NULL
                   ), 0) AS pending_payout
            FROM sellers s JOIN users u ON u.id = s.user_id
            ORDER BY CASE s.status WHEN 'PENDING' THEN 0 ELSE 1 END, s.created_at DESC
            """
        ).fetchall()
        totals = connection.execute(
            """
            SELECT COALESCE(SUM(so.commission_amount), 0)
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            WHERE o.payment_status = 'paid'
            """
        ).fetchone()[0]
        payout_rows = connection.execute(
            """
            SELECT pt.id, pt.seller_id, s.store_name, pt.amount,
                   pt.commission_retained, pt.payout_method, pt.reference,
                   pt.transaction_id, pt.status, pt.failure_reason,
                   pt.paid_by, pt.created_at
            FROM payout_transactions pt JOIN sellers s ON s.id = pt.seller_id
            ORDER BY pt.created_at DESC LIMIT 100
            """
        ).fetchall()
        payable_rows = connection.execute(
            """
            SELECT so.id, so.seller_id, so.seller_payout_amount, o.order_number
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN payout_allocations pa ON pa.sub_order_id = so.id
            WHERE o.payment_status = 'paid' AND so.fulfillment_status = 'DELIVERED'
              AND pa.sub_order_id IS NULL
            ORDER BY o.created_at
            """
        ).fetchall()
    payable_by_seller: dict[int, list[dict]] = {}
    for row in payable_rows:
        payable_by_seller.setdefault(row["seller_id"], []).append(
            {
                "id": row["id"],
                "amount": row["seller_payout_amount"],
                "order_number": row["order_number"],
            }
        )
    serialized_vendors = []
    for row in vendors:
        vendor = dict(row)
        vendor["submitted_documents"] = json.loads(
            vendor.pop("submitted_documents_json")
        )
        vendor["pending_sub_orders"] = payable_by_seller.get(vendor["id"], [])
        serialized_vendors.append(vendor)
    return {
        "vendors": serialized_vendors,
        "total_commissions": round(totals, 2),
        "pending_payouts": round(sum(row["pending_payout"] for row in vendors), 2),
        "payout_transactions": [dict(row) for row in payout_rows],
    }


@router.post("/marketplace/vendors/{seller_id}/review")
def review_marketplace_vendor(
    seller_id: int, review: SellerReviewUpdate, request: Request
) -> dict:
    username = _authorize(request, "settings", "write")
    _verify_admin_write(request)
    review_changes = {
        "APPROVE": ("APPROVED", "CLEAR", "VENDOR_APPROVED"),
        "REJECT": ("SUSPENDED", "CLEAR", "VENDOR_REJECTED"),
        "REQUEST_INFO": (None, None, "VENDOR_INFO_REQUESTED"),
        "SUSPEND": ("SUSPENDED", "CLEAR", "VENDOR_SUSPENDED"),
        "UNDER_AUDIT": ("APPROVED", "UNDER_AUDIT", "VENDOR_UNDER_AUDIT"),
        "RESTORE": ("APPROVED", "CLEAR", "VENDOR_RESTORED"),
    }
    next_status, review_state, event_type = review_changes[review.action]
    with get_connection() as connection:
        seller = connection.execute(
            "SELECT store_name FROM sellers WHERE id = ?", (seller_id,)
        ).fetchone()
        if seller is None:
            raise HTTPException(status_code=404, detail="Seller application was not found.")
        if next_status is None:
            connection.execute(
                "UPDATE sellers SET review_note = ? WHERE id = ?",
                (review.reason, seller_id),
            )
        else:
            connection.execute(
                """
                UPDATE sellers SET status = ?, review_state = ?, review_note = ?
                WHERE id = ?
                """,
                (next_status, review_state, review.reason, seller_id),
            )
            if review.action == "APPROVE":
                connection.execute(
                    "UPDATE seller_profiles SET status = 'approved' WHERE seller_id = ?",
                    (seller_id,),
                )
            elif review.action == "REJECT":
                connection.execute(
                    "UPDATE seller_profiles SET status = 'pending' WHERE seller_id = ?",
                    (seller_id,),
                )
        _audit(
            connection,
            request,
            "Marketplace",
            event_type,
            f"{review.action.replace('_', ' ').title()} for seller {seller['store_name']}.",
            severity="WARNING" if review.action in {"REJECT", "SUSPEND", "UNDER_AUDIT"} else "INFO",
            details={
                "seller_id": seller_id,
                "seller_name": seller["store_name"],
                "action": review.action,
                "reason": review.reason,
                "admin": username,
            },
        )
        connection.commit()
    return {
        "seller_id": seller_id,
        "action": review.action,
        "status": next_status or "PENDING",
        "review_note": review.reason,
    }


@router.get("/marketplace/commissions")
def marketplace_commission_settings(request: Request) -> dict:
    _authorize(request, "settings", "write")
    with get_connection() as connection:
        default = connection.execute(
            "SELECT value FROM store_settings WHERE key = 'marketplace_default_commission'"
        ).fetchone()
        category_rates = connection.execute(
            """
            SELECT category, percentage FROM marketplace_commission_category_rates
            WHERE seller_id = 0 ORDER BY category
            """
        ).fetchall()
        seller_rates = connection.execute(
            """
            SELECT id AS seller_id, commission_percentage
            FROM sellers WHERE commission_is_custom = 1
            """
        ).fetchall()
        seller_category_rates = connection.execute(
            """
            SELECT seller_id, category, percentage
            FROM marketplace_commission_category_rates
            WHERE seller_id != 0 ORDER BY seller_id, category
            """
        ).fetchall()
    return {
        "default_percentage": float(default["value"]) if default else 10,
        "category_rates": {
            row["category"]: row["percentage"] for row in category_rates
        },
        "seller_rates": {
            str(row["seller_id"]): row["commission_percentage"]
            for row in seller_rates
        },
        "seller_category_rates": [
            {
                "seller_id": row["seller_id"],
                "category": row["category"],
                "percentage": row["percentage"],
            }
            for row in seller_category_rates
        ],
    }


@router.put("/marketplace/commissions")
def update_marketplace_commission_settings(
    settings: CommissionSettingsUpdate, request: Request
) -> dict:
    username = _authorize(request, "settings", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        unknown_sellers = set(settings.seller_rates) | set(settings.seller_category_rates)
        if unknown_sellers:
            placeholders = ",".join("?" for _ in unknown_sellers)
            existing = {
                row["id"]
                for row in connection.execute(
                    f"SELECT id FROM sellers WHERE id IN ({placeholders})",
                    tuple(unknown_sellers),
                )
            }
            if existing != unknown_sellers:
                raise HTTPException(status_code=404, detail="A commission seller was not found.")
        connection.execute(
            """
            INSERT INTO store_settings (key, value)
            VALUES ('marketplace_default_commission', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(settings.default_percentage),),
        )
        connection.execute(
            "DELETE FROM marketplace_commission_category_rates WHERE seller_id = 0"
        )
        connection.executemany(
            """
            INSERT INTO marketplace_commission_category_rates (
                seller_id, category, percentage
            ) VALUES (0, ?, ?)
            """,
            list(settings.category_rates.items()),
        )
        connection.execute(
            "UPDATE sellers SET commission_is_custom = 0"
        )
        for seller_id, percentage in settings.seller_rates.items():
            connection.execute(
                """
                UPDATE sellers SET commission_percentage = ?, commission_is_custom = 1
                WHERE id = ?
                """,
                (percentage, seller_id),
            )
        connection.execute(
            "DELETE FROM marketplace_commission_category_rates WHERE seller_id != 0"
        )
        connection.executemany(
            """
            INSERT INTO marketplace_commission_category_rates (
                seller_id, category, percentage
            ) VALUES (?, ?, ?)
            """,
            [
                (seller_id, category, percentage)
                for seller_id, rates in settings.seller_category_rates.items()
                for category, percentage in rates.items()
            ],
        )
        _audit(
            connection,
            request,
            "Marketplace",
            "COMMISSION_SETTINGS_UPDATED",
            "Updated marketplace default, category, and seller commission rates.",
            details={
                "default_percentage": settings.default_percentage,
                "category_rates": settings.category_rates,
                "seller_rates": settings.seller_rates,
                "seller_category_rates": settings.seller_category_rates,
                "admin": username,
            },
        )
        connection.commit()
    return {"updated": True}


@router.patch("/marketplace/vendors/{seller_id}")
def update_marketplace_vendor(
    seller_id: int, update: SellerStatusUpdate, request: Request
) -> dict:
    username = _authorize(request, "settings", "write")
    _verify_admin_write(request)
    next_status = update.status
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE sellers SET status = ? WHERE id = ?",
            (next_status, seller_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Vendor application was not found.")
        if next_status == "APPROVED":
            connection.execute(
                "UPDATE seller_profiles SET status = 'approved' WHERE seller_id = ?",
                (seller_id,),
            )
        elif next_status == "PENDING":
            connection.execute(
                "UPDATE seller_profiles SET status = 'pending' WHERE seller_id = ?",
                (seller_id,),
            )
        _audit(
            connection,
            request,
            "Marketplace",
            "VENDOR_STATUS_UPDATED",
            f"Set seller {seller_id} status to {next_status}.",
            details={"seller_id": seller_id, "status": next_status, "admin": username},
        )
        connection.commit()
    return {"seller_id": seller_id, "status": next_status}


@router.post("/marketplace/payouts", status_code=status.HTTP_201_CREATED)
def create_marketplace_payout(
    payout: SellerPayoutInput, request: Request
) -> dict:
    username = _authorize(request, "settings", "write")
    _verify_admin_write(request)
    unique_ids = list(dict.fromkeys(payout.sub_order_ids))
    placeholders = ",".join("?" for _ in unique_ids)
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            f"""
            SELECT so.id, so.seller_payout_amount, so.commission_amount,
                   s.payout_method
            FROM sub_orders so JOIN sellers s ON s.id = so.seller_id
            JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN payout_allocations pa ON pa.sub_order_id = so.id
            WHERE so.seller_id = ? AND so.id IN ({placeholders})
              AND o.payment_status = 'paid' AND so.fulfillment_status = 'DELIVERED'
              AND pa.sub_order_id IS NULL
            """,
            (payout.seller_id, *unique_ids),
        ).fetchall()
        if len(rows) != len(unique_ids):
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="Every selected sub-order must be paid, delivered, unpaid, and owned by this seller.",
            )
        amount = round(sum(row["seller_payout_amount"] for row in rows), 2)
        commission_retained = round(sum(row["commission_amount"] for row in rows), 2)
        if amount <= 0:
            connection.rollback()
            raise HTTPException(status_code=409, detail="No payable balance was selected.")
        payout_method = rows[0]["payout_method"]
        try:
            cursor = connection.execute(
                """
                INSERT INTO payout_transactions (
                    seller_id, amount, commission_retained, payout_method,
                    reference, status, paid_by
                ) VALUES (?, ?, ?, ?, ?, 'PROCESSING', ?)
                """,
                (
                    payout.seller_id,
                    amount,
                    commission_retained,
                    payout_method,
                    payout.reference,
                    username,
                ),
            )
            connection.executemany(
                """
                INSERT INTO payout_allocations (payout_transaction_id, sub_order_id)
                VALUES (?, ?)
                """,
                [(cursor.lastrowid, sub_order_id) for sub_order_id in unique_ids],
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="That payout reference or seller order has already been recorded.",
            ) from error
        _audit(
            connection,
            request,
            "Marketplace",
            "SELLER_PAYOUT_RECORDED",
            f"Recorded {amount:.2f} KES payout for seller {payout.seller_id}.",
            details={
                "seller_id": payout.seller_id,
                "sub_order_ids": unique_ids,
                "amount": amount,
                "commission_retained": commission_retained,
                "reference": payout.reference,
                "dispatch_status": "PROCESSING",
            },
        )
        connection.commit()
    return {
        "id": cursor.lastrowid,
        "seller_id": payout.seller_id,
        "amount": amount,
        "commission_retained": commission_retained,
        "payout_method": payout_method,
        "reference": payout.reference,
        "status": "PROCESSING",
    }


@router.patch("/marketplace/payouts/{payout_id}")
def update_marketplace_payout(
    payout_id: int, update: MarketplacePayoutUpdate, request: Request
) -> dict:
    username = _authorize(request, "settings", "write")
    _verify_admin_write(request)
    if update.status == "COMPLETED" and not update.transaction_id.strip():
        raise HTTPException(
            status_code=422,
            detail="Enter the M-Pesa or bank transaction ID to complete a payout.",
        )
    with get_connection() as connection:
        payout = connection.execute(
            "SELECT status, reference FROM payout_transactions WHERE id = ?",
            (payout_id,),
        ).fetchone()
        if payout is None:
            raise HTTPException(status_code=404, detail="Payout dispatch was not found.")
        if payout["status"] in {"COMPLETED", "FAILED"}:
            raise HTTPException(
                status_code=409,
                detail="A completed or failed payout cannot be changed.",
            )
        connection.execute(
            """
            UPDATE payout_transactions
            SET status = ?, transaction_id = ?, failure_reason = ?
            WHERE id = ?
            """,
            (
                update.status,
                update.transaction_id.strip(),
                update.failure_reason,
                payout_id,
            ),
        )
        if update.status == "FAILED":
            connection.execute(
                "DELETE FROM payout_allocations WHERE payout_transaction_id = ?",
                (payout_id,),
            )
        _audit(
            connection,
            request,
            "Marketplace",
            "SELLER_PAYOUT_STATUS_UPDATED",
            f"Payout {payout['reference']} marked {update.status}.",
            severity="WARNING" if update.status == "FAILED" else "INFO",
            details={
                "payout_id": payout_id,
                "reference": payout["reference"],
                "status": update.status,
                "transaction_id": update.transaction_id,
                "failure_reason": update.failure_reason,
                "admin": username,
            },
        )
        connection.commit()
    return {
        "id": payout_id,
        "status": update.status,
        "transaction_id": update.transaction_id,
    }


@router.get("/marketplace/orders")
def marketplace_orders(
    request: Request,
    seller_id: int | None = Query(default=None, gt=0),
    status_filter: str = Query(default="", alias="status", max_length=20),
) -> list[dict]:
    _authorize(request, "orders", "read")
    if status_filter and status_filter not in {
        "PENDING",
        "PROCESSING",
        "SHIPPED",
        "DELIVERED",
    }:
        raise HTTPException(status_code=422, detail="Unsupported seller order status.")
    conditions = []
    parameters: list[object] = []
    if seller_id is not None:
        conditions.append("so.seller_id = ?")
        parameters.append(seller_id)
    if status_filter:
        conditions.append("so.fulfillment_status = ?")
        parameters.append(status_filter)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT so.id, so.parent_order_id, so.seller_id, so.items_json,
                   so.subtotal, so.commission_amount, so.seller_payout_amount,
                   so.fulfillment_status, s.store_name, o.order_number,
                   o.customer_name, o.customer_phone, o.delivery_address,
                   o.payment_status, o.created_at
            FROM sub_orders so JOIN sellers s ON s.id = so.seller_id
            JOIN orders o ON o.id = so.parent_order_id
            {where_clause}
            ORDER BY o.created_at DESC, so.id
            """,
            parameters,
        ).fetchall()
        disputes = connection.execute(
            """
            SELECT md.*, so.parent_order_id, so.seller_id
            FROM marketplace_disputes md JOIN sub_orders so ON so.id = md.sub_order_id
            ORDER BY md.created_at DESC
            """
        ).fetchall()
    disputes_by_sub_order: dict[int, list[dict]] = {}
    for row in disputes:
        disputes_by_sub_order.setdefault(row["sub_order_id"], []).append(
            {
                "id": row["id"],
                "action": row["action"],
                "reason": row["reason"],
                "amount": row["amount"],
                "status": row["status"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            }
        )
    sub_orders = []
    for row in rows:
        sub_orders.append(
            {
                "id": row["id"],
                "parent_order_id": row["parent_order_id"],
                "order_number": row["order_number"],
                "seller_id": row["seller_id"],
                "seller_name": row["store_name"],
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
                "payment_status": row["payment_status"],
                "created_at": row["created_at"],
                "disputes": disputes_by_sub_order.get(row["id"], []),
            }
        )
    return sub_orders


@router.get("/marketplace/orders/sellers")
def marketplace_order_sellers(request: Request) -> list[dict]:
    _authorize(request, "orders", "read")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT s.id, s.store_name FROM sellers s
            WHERE EXISTS (SELECT 1 FROM sub_orders so WHERE so.seller_id = s.id)
            ORDER BY s.store_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/marketplace/orders/{sub_order_id}/disputes", status_code=201)
def create_marketplace_dispute(
    sub_order_id: int, dispute: MarketplaceDisputeInput, request: Request
) -> dict:
    username = _authorize(request, "orders", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        order = connection.execute(
            """
            SELECT id, seller_id, subtotal, seller_payout_amount
            FROM sub_orders WHERE id = ?
            """,
            (sub_order_id,),
        ).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Seller order was not found.")
        if dispute.action in {"PENALTY_RECORDED", "REFUND_RECORDED"} and dispute.amount <= 0:
            raise HTTPException(
                status_code=422,
                detail="Enter a positive amount for a recorded refund or vendor penalty.",
            )
        maximum_amount = (
            order["subtotal"]
            if dispute.action == "REFUND_RECORDED"
            else order["seller_payout_amount"]
        )
        if dispute.action in {"PENALTY_RECORDED", "REFUND_RECORDED"} and dispute.amount > maximum_amount:
            raise HTTPException(
                status_code=422,
                detail="The recorded amount cannot exceed the seller order value.",
            )
        cursor = connection.execute(
            """
            INSERT INTO marketplace_disputes (
                sub_order_id, action, reason, amount, status, created_by
            ) VALUES (?, ?, ?, ?, 'RECORDED', ?)
            """,
            (
                sub_order_id,
                dispute.action,
                dispute.reason,
                dispute.amount,
                username,
            ),
        )
        _audit(
            connection,
            request,
            "Marketplace",
            "MARKETPLACE_DISPUTE_ACTION",
            f"{dispute.action.replace('_', ' ').title()} recorded for seller order {sub_order_id}.",
            severity="WARNING",
            details={
                "dispute_id": cursor.lastrowid,
                "sub_order_id": sub_order_id,
                "seller_id": order["seller_id"],
                "action": dispute.action,
                "reason": dispute.reason,
                "amount": dispute.amount,
                "admin": username,
            },
        )
        connection.commit()
    return {"id": cursor.lastrowid, "sub_order_id": sub_order_id, "status": "RECORDED"}


@router.get("/marketplace/analytics")
def marketplace_analytics(request: Request) -> dict:
    _authorize(request, "analytics", "read")
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN o.payment_status = 'paid'
                    THEN o.subtotal_cents ELSE 0 END), 0) / 100.0 AS gmv,
                   COALESCE(SUM(CASE WHEN o.payment_status = 'paid'
                    THEN so.commission_amount ELSE 0 END), 0) AS platform_revenue
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            """
        ).fetchone()
        payout_total = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM payout_transactions
            WHERE status = 'COMPLETED' AND paid_by != 'seller_demo'
            """
        ).fetchone()[0]
        seller_count = connection.execute(
            """
            SELECT COUNT(*) FROM sellers
            WHERE status = 'APPROVED' AND review_state = 'CLEAR'
            """
        ).fetchone()[0]
        top_sellers = connection.execute(
            """
            SELECT s.id, s.store_name, s.rating,
                   COALESCE(SUM(CASE WHEN o.payment_status = 'paid'
                       THEN so.subtotal ELSE 0 END), 0) AS revenue,
                   COUNT(DISTINCT CASE WHEN o.payment_status = 'paid'
                       THEN so.parent_order_id END) AS orders
            FROM sellers s LEFT JOIN sub_orders so ON so.seller_id = s.id
            LEFT JOIN orders o ON o.id = so.parent_order_id
            WHERE s.status = 'APPROVED' AND s.review_state = 'CLEAR'
            GROUP BY s.id ORDER BY revenue DESC LIMIT 10
            """
        ).fetchall()
    return {
        "gmv": round(totals["gmv"], 2),
        "platform_net_revenue": round(totals["platform_revenue"], 2),
        "vendor_payouts": round(payout_total, 2),
        "active_sellers": seller_count,
        "top_vendors": [dict(row) for row in top_sellers],
    }
def _serialize_order(row: sqlite3.Row, items: list[dict] | None = None) -> dict:
    subtotal = row["subtotal_cents"] / 100
    shipping = row["shipping_cents"] / 100
    tax = row["tax_cents"] / 100
    return {
        "id": row["id"],
        "order_number": row["order_number"],
        "customer": {
            "name": row["customer_name"],
            "phone": row["customer_phone"],
            "address": row["delivery_address"],
        },
        "payment_method": row["payment_method"],
        "payment_gateway": row["payment_gateway"],
        "gateway_reference": row["gateway_reference"],
        "gateway_status": row["gateway_status"],
        "payment_status": row["payment_status"],
        "status": row["status"],
        "subtotal": subtotal,
        "shipping": shipping,
        "tax": tax,
        "total": row["total_cents"] / 100,
        "created_at": row["created_at"],
        "items": items or [],
    }


def _product_values(product: ProductAdminInput, product_id: str) -> dict:
    images = product.images
    details = product.details
    discount = ""
    if product.oldPrice and product.oldPrice > product.price:
        percent = round((product.oldPrice - product.price) / product.oldPrice * 100)
        discount = f"-{percent}%"
    category = product.category
    return {
        "id": product_id,
        "name": product.name,
        "brand": product.brand,
        "sku": product.sku.upper(),
        "category": category,
        "detail": product.detail,
        "price": product.price,
        "unit_cost": product.unitCost,
        "old_price": product.oldPrice,
        "discount": discount,
        "rating": product.rating,
        "reviews_count": product.reviewsCount,
        "tag": product.tag,
        "tag_color": product.tagColor,
        "description": product.description,
        "stock": product.stock,
        "low_stock_threshold": product.lowStockThreshold,
        "image": images[0],
        "gallery_json": json.dumps(images),
        "notes_json": json.dumps([]),
        "nail_sizes_json": json.dumps(details.get("availableSizes", [])),
        "highlights_json": json.dumps([]),
        "details_json": json.dumps(details),
        "tone": (
            "rose"
            if "Perfumes" in category or "Makeup" in category
            else "peach"
            if "Nails" in category
            else "cream"
            if "Skincare" in category
            else "lilac"
        ),
        "active": int(product.active),
    }


def _upsert_product(connection: sqlite3.Connection, values: dict) -> None:
    connection.execute(
        """
        INSERT INTO products (
            id, name, brand, sku, category, detail, price, unit_cost, old_price, discount,
            rating, reviews_count, tag, tag_color, description, stock,
            low_stock_threshold, image, gallery_json, notes_json,
            nail_sizes_json, highlights_json, details_json, tone, active
        ) VALUES (
            :id, :name, :brand, :sku, :category, :detail, :price, :unit_cost, :old_price,
            :discount, :rating, :reviews_count, :tag, :tag_color, :description,
            :stock, :low_stock_threshold, :image, :gallery_json, :notes_json,
            :nail_sizes_json, :highlights_json, :details_json, :tone, :active
        )
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, brand=excluded.brand, sku=excluded.sku,
            category=excluded.category, detail=excluded.detail, price=excluded.price,
            old_price=excluded.old_price, discount=excluded.discount,
            rating=excluded.rating, reviews_count=excluded.reviews_count,
            tag=excluded.tag, tag_color=excluded.tag_color,
            description=excluded.description, stock=excluded.stock,
            low_stock_threshold=excluded.low_stock_threshold, image=excluded.image,
            gallery_json=excluded.gallery_json, notes_json=excluded.notes_json,
            nail_sizes_json=excluded.nail_sizes_json, highlights_json=excluded.highlights_json,
            details_json=excluded.details_json, tone=excluded.tone, active=excluded.active,
            unit_cost=excluded.unit_cost
        """,
        values,
    )


@router.post("/login")
def admin_login(
    payload: AdminLogin, request: Request, response: Response
) -> dict:
    result = login_admin(payload.username, payload.password, request, response)
    result["permissions"] = _role_permissions(result["role"])
    return result


@router.post("/logout")
def admin_logout(request: Request, response: Response) -> dict:
    if current_admin(request):
        _verify_admin_write(request)
    return logout_admin(request, response)


@router.get("/session")
def admin_session(request: Request) -> dict:
    identity = current_admin_details(request)
    if not identity:
        return {"authenticated": False}
    return {
        "authenticated": True,
        **identity,
        "permissions": _role_permissions(identity["role"]),
    }


@router.get("/overview")
def admin_overview(
    request: Request,
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly)$"),
) -> dict:
    _authorize(request, "analytics", "read")
    can_read_orders = _role_permissions(
        request.state.admin_identity["role"]
    ).get("orders", {}).get("read", False)
    now = datetime.now(timezone.utc)
    period_spec = {
        "daily": (7, "day", "%Y-%m-%d"),
        "weekly": (8, "week", "%Y-%W"),
        "monthly": (12, "month", "%Y-%m"),
    }
    count, interval, date_format = period_spec[period]
    with get_connection() as connection:
        if interval == "day":
            start = (now - timedelta(days=count - 1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif interval == "week":
            start = (now - timedelta(weeks=count - 1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start -= timedelta(days=start.weekday())
        else:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            for _ in range(count - 1):
                start = (start.replace(day=1) - timedelta(days=1)).replace(day=1)

        previous_start = start
        if interval == "day":
            previous_start -= timedelta(days=count)
        elif interval == "week":
            previous_start -= timedelta(weeks=count)
        else:
            for _ in range(count):
                previous_start = (
                    previous_start.replace(day=1) - timedelta(days=1)
                ).replace(day=1)

        report_orders = connection.execute(
            """
            SELECT * FROM orders
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            """,
            (
                previous_start.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        ).fetchall()
        orders = [
            row
            for row in report_orders
            if datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ) >= start
        ]
        previous_orders = [
            row
            for row in report_orders
            if datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ) < start
        ]
        all_order_metrics = connection.execute(
            """
            SELECT COUNT(*) AS order_count,
                   COALESCE(SUM(total_cents), 0) AS revenue_cents
            FROM orders
            WHERE status != 'cancelled' AND payment_status = 'paid'
            """
        ).fetchone()
        total_orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        customer_count = connection.execute(
            """
            SELECT COUNT(DISTINCT customer_phone) FROM orders
            WHERE status != 'cancelled' AND payment_status = 'paid'
              AND created_at >= ? AND created_at <= ?
            """,
            (
                (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        ).fetchone()[0]
        previous_customer_count = connection.execute(
            """
            SELECT COUNT(DISTINCT customer_phone) FROM orders
            WHERE status != 'cancelled' AND payment_status = 'paid'
              AND created_at >= ? AND created_at < ?
            """,
            (
                (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        ).fetchone()[0]
        low_stock_count = connection.execute(
            """
            SELECT COUNT(*) FROM products
            WHERE active = 1 AND stock <= low_stock_threshold
            """
        ).fetchone()[0]
        product_count = connection.execute(
            "SELECT COUNT(*) FROM products WHERE active = 1"
        ).fetchone()[0]

        period_orders: dict[str, dict[str, int]] = {}
        for row in orders:
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            key = created.strftime(date_format)
            aggregate = period_orders.setdefault(key, {"orders": 0, "revenue": 0})
            aggregate["orders"] += 1
            if row["status"] != "cancelled" and row["payment_status"] == "paid":
                aggregate["revenue"] += row["total_cents"]

        chart = []
        cursor = start
        for _ in range(count):
            key = cursor.strftime(date_format)
            chart.append(
                {
                    "label": cursor.strftime("%a" if interval == "day" else "%b %d" if interval == "week" else "%b"),
                    "revenue": period_orders.get(key, {}).get("revenue", 0) / 100,
                    "orders": period_orders.get(key, {}).get("orders", 0),
                }
            )
            if interval == "day":
                cursor += timedelta(days=1)
            elif interval == "week":
                cursor += timedelta(weeks=1)
            else:
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

        recent_rows = (
            connection.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT 8"
            ).fetchall()
            if can_read_orders
            else []
        )
        top_rows = connection.execute(
            """
            SELECT oi.product_name, oi.product_id, SUM(oi.quantity) AS units,
                   SUM(oi.unit_price_cents * oi.quantity) AS revenue_cents
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.status != 'cancelled' AND o.payment_status = 'paid'
            GROUP BY oi.product_id, oi.product_name
            ORDER BY units DESC, revenue_cents DESC
            LIMIT 8
            """
        ).fetchall()

    def period_metrics(rows: list[sqlite3.Row]) -> tuple[int, int, int]:
        valid_orders = [
            row
            for row in rows
            if row["status"] != "cancelled" and row["payment_status"] == "paid"
        ]
        return (
            len(rows),
            sum(row["total_cents"] for row in valid_orders),
            len(valid_orders),
        )

    def percentage_change(current: float, previous: float) -> float:
        if previous == 0:
            return 100 if current > 0 else 0
        return round((current - previous) / previous * 100, 1)

    (
        current_period_orders,
        current_period_revenue,
        current_period_active_orders,
    ) = period_metrics(orders)
    (
        previous_period_orders,
        previous_period_revenue,
        previous_period_active_orders,
    ) = period_metrics(previous_orders)
    current_aov = (
        current_period_revenue / current_period_active_orders
        if current_period_active_orders
        else 0
    )
    previous_aov = (
        previous_period_revenue / previous_period_active_orders
        if previous_period_active_orders
        else 0
    )
    total_revenue_cents = all_order_metrics["revenue_cents"]
    active_order_count = all_order_metrics["order_count"]

    return {
        "currency": "KES",
        "period": period,
        "kpis": {
            "revenue": total_revenue_cents / 100,
            "orders": total_orders,
            "average_order_value": (
                total_revenue_cents / active_order_count / 100
                if active_order_count
                else 0
            ),
            "active_customers": customer_count,
            "low_stock": low_stock_count,
            "products": product_count,
        },
        "trends": {
            "revenue_percent": percentage_change(
                current_period_revenue, previous_period_revenue
            ),
            "orders_percent": percentage_change(
                current_period_orders, previous_period_orders
            ),
            "aov_percent": percentage_change(current_aov, previous_aov),
            "customers_percent": percentage_change(
                customer_count, previous_customer_count
            ),
        },
        "chart": chart,
        "recent_orders": [_serialize_order(row) for row in recent_rows],
        "top_products": [
            {
                "id": row["product_id"],
                "name": row["product_name"],
                "units_sold": row["units"],
                "revenue": row["revenue_cents"] / 100,
            }
            for row in top_rows
        ],
    }


@router.get("/products")
def admin_products(request: Request, search: str = Query(default="", max_length=100)) -> list[dict]:
    _authorize(request, "products", "read")
    with get_connection() as connection:
        if search.strip():
            rows = connection.execute(
                """
                SELECT * FROM products
                WHERE active = 1 AND lower(name || ' ' || brand || ' ' || sku) LIKE lower(?)
                ORDER BY name
                """,
                (f"%{search.strip()}%",),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM products WHERE active = 1 ORDER BY name"
            ).fetchall()
    return [serialize_product(row, include_internal=True) for row in rows]


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(product: ProductAdminInput, request: Request) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    product_id = f"custom-{uuid.uuid4().hex[:12]}"
    values = _product_values(product, product_id)
    try:
        with get_connection() as connection:
            _upsert_product(connection, values)
            _audit(
                connection,
                request,
                "Inventory",
                "PRODUCT_CREATED",
                f"Created product {product.name} ({product_id}).",
                details={"product_id": product_id, "sku": product.sku},
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="That SKU is already in use.") from error
    return serialize_product(row, include_internal=True)


@router.put("/products/{product_id}")
def update_product(
    product_id: str, product: ProductAdminInput, request: Request
) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, name, price, unit_cost, stock FROM products WHERE id = ? AND active = 1", (product_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        try:
            _upsert_product(connection, _product_values(product, product_id))
            category = (
                "Pricing"
                if existing["price"] != product.price or existing["unit_cost"] != product.unitCost
                else "Inventory"
            )
            description = (
                f"Updated price or cost for {product.name}."
                if category == "Pricing"
                else f"Updated product details for {product.name}."
            )
            _audit(
                connection,
                request,
                category,
                "PRODUCT_UPDATED",
                description,
                details={
                    "product_id": product_id,
                    "price_before": existing["price"],
                    "price_after": product.price,
                    "unit_cost_before": existing["unit_cost"],
                    "unit_cost_after": product.unitCost,
                },
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="That SKU is already in use.") from error
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    return serialize_product(row, include_internal=True)


@router.post("/products/{product_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_product(product_id: str, request: Request) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        source = connection.execute(
            "SELECT * FROM products WHERE id = ? AND active = 1", (product_id,)
        ).fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        copy = dict(source)
        new_id = f"copy-{uuid.uuid4().hex[:12]}"
        copy["id"] = new_id
        copy["name"] = f"{copy['name']} (Copy)"
        copy["sku"] = f"{copy['sku'] or product_id}-COPY-{secrets.token_hex(2)}".upper()
        connection.execute(
            """
            INSERT INTO products (
                id, name, brand, sku, category, detail, price, unit_cost, old_price, discount,
                rating, reviews_count, tag, tag_color, description, stock,
                low_stock_threshold, image, gallery_json, notes_json,
                nail_sizes_json, highlights_json, details_json, tone, active
            ) VALUES (
                :id, :name, :brand, :sku, :category, :detail, :price, :unit_cost, :old_price,
                :discount, :rating, :reviews_count, :tag, :tag_color, :description,
                :stock, :low_stock_threshold, :image, :gallery_json, :notes_json,
                :nail_sizes_json, :highlights_json, :details_json, :tone, 1
            )
            """,
            copy,
        )
        _audit(
            connection,
            request,
            "Inventory",
            "PRODUCT_DUPLICATED",
            f"Duplicated product {source['name']} as {copy['name']}.",
            details={"source_product_id": product_id, "product_id": new_id},
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (new_id,)
        ).fetchone()
    return serialize_product(row, include_internal=True)


@router.delete("/products/{product_id}")
def delete_product(product_id: str, request: Request) -> dict[str, str]:
    _authorize(request, "products", "delete")
    _verify_admin_write(request)
    with get_connection() as connection:
        product = connection.execute(
            "SELECT name FROM products WHERE id = ? AND active = 1",
            (product_id,),
        ).fetchone()
        cursor = connection.execute(
            "UPDATE products SET active = 0 WHERE id = ? AND active = 1",
            (product_id,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found.")
        _audit(
            connection,
            request,
            "Inventory",
            "PRODUCT_DELETED",
            f"Removed product {product['name']} from the storefront.",
            "WARNING",
            {"product_id": product_id},
        )
        connection.commit()
    return {"message": "Product removed from the storefront."}


@router.patch("/products/{product_id}/stock")
def update_product_stock(
    product_id: str,
    request: Request,
    stock: int = Query(ge=0, le=1_000_000),
) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        before = connection.execute(
            "SELECT name, stock FROM products WHERE id = ? AND active = 1",
            (product_id,),
        ).fetchone()
        cursor = connection.execute(
            "UPDATE products SET stock = ? WHERE id = ? AND active = 1",
            (stock, product_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found.")
        _audit(
            connection,
            request,
            "Inventory",
            "STOCK_UPDATED",
            f"Updated stock for {before['name']} from {before['stock']} to {stock}.",
            details={
                "product_id": product_id,
                "before": before["stock"],
                "after": stock,
            },
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
    return serialize_product(row, include_internal=True)


def _serialize_fulfillment_order(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    items = decoded_items(row["items_json"])
    disputes = connection.execute(
        """
        SELECT id, action, reason, amount, status, created_by, created_at
        FROM marketplace_disputes
        WHERE sub_order_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "parent_order_id": row["parent_order_id"],
        "order_number": row["order_number"],
        "tracking_id": row["tracking_id"],
        "seller_id": row["seller_id"],
        "seller_name": row["store_name"],
        "customer": {
            "name": row["customer_name"],
            "phone": row["customer_phone"],
            "address": row["delivery_address"],
        },
        "items": items,
        "subtotal": row["subtotal"],
        "commission_amount": row["commission_amount"],
        "seller_payout_amount": row["seller_payout_amount"],
        "total": row["total_cents"] / 100,
        "shipping": row["shipping_cents"] / 100,
        "fulfillment_status": effective_fulfillment_status(row),
        "payment_status": row["payment_status"],
        "courier_name": row["courier_name"],
        "tracking_number": row["tracking_number"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "timeline": status_timeline(connection, row["id"]),
        "disputes": [dict(dispute) for dispute in disputes],
    }


@router.get("/orders")
def admin_orders(
    request: Request,
    order_status: str = Query(default="all", alias="status"),
    search: str = Query(default="", max_length=100),
    scope: str = Query(default="orders", pattern="^(orders|fulfillment)$"),
    vendor_id: int | None = Query(default=None, ge=1),
) -> list[dict]:
    _authorize(request, "orders", "read")
    if scope == "fulfillment":
        if order_status != "all" and order_status not in {
            "PENDING_PACKING",
            "PACKED",
            "PACKED_AND_READY",
            "DISPATCHED_TO_COURIER",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "CANCELLED",
        }:
            raise HTTPException(status_code=422, detail="Unknown fulfillment status.")
        conditions = []
        parameters: list[object] = []
        if vendor_id is not None:
            conditions.append("so.seller_id = ?")
            parameters.append(vendor_id)
        if order_status != "all":
            conditions.append(
                """
                COALESCE(
                    NULLIF(so.admin_override_status, ''),
                    CASE so.fulfillment_status
                        WHEN 'PENDING' THEN 'PENDING_PACKING'
                        WHEN 'PROCESSING' THEN 'PACKED'
                        WHEN 'SHIPPED' THEN 'DISPATCHED_TO_COURIER'
                        ELSE so.fulfillment_status
                    END
                ) = ?
                """
            )
            parameters.append(order_status)
        if search.strip():
            term = f"%{search.strip()}%"
            conditions.append(
                """
                (o.order_number LIKE ? COLLATE NOCASE
                 OR o.tracking_id LIKE ? COLLATE NOCASE
                 OR o.customer_name LIKE ? COLLATE NOCASE
                 OR o.customer_phone LIKE ? COLLATE NOCASE
                 OR o.delivery_address LIKE ? COLLATE NOCASE
                 OR s.store_name LIKE ? COLLATE NOCASE
                 OR so.courier_name LIKE ? COLLATE NOCASE
                 OR so.tracking_number LIKE ? COLLATE NOCASE)
                """
            )
            parameters.extend([term] * 8)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT so.id, so.parent_order_id, so.seller_id, so.items_json,
                       so.subtotal, so.commission_amount, so.seller_payout_amount,
                       so.fulfillment_status, so.admin_override_status,
                       so.courier_name, so.tracking_number, so.updated_at,
                       s.store_name, o.order_number, o.tracking_id,
                       o.customer_name, o.customer_phone, o.delivery_address,
                       o.payment_status, o.total_cents, o.shipping_cents,
                       o.created_at
                FROM sub_orders so
                JOIN sellers s ON s.id = so.seller_id
                JOIN orders o ON o.id = so.parent_order_id
                {where_clause}
                ORDER BY o.created_at DESC, so.id DESC
                """,
                parameters,
            ).fetchall()
            return [_serialize_fulfillment_order(connection, row) for row in rows]

    if order_status != "all" and order_status not in ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown order status.")
    conditions = []
    parameters: list[object] = []
    if order_status != "all":
        conditions.append("status = ?")
        parameters.append(order_status)
    if search.strip():
        term = f"%{search.strip().casefold()}%"
        conditions.append(
            "(lower(order_number) LIKE ? OR lower(customer_name) LIKE ? OR lower(customer_phone) LIKE ?)"
        )
        parameters.extend([term, term, term])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM orders {where_clause} ORDER BY created_at DESC LIMIT 200",
            parameters,
        ).fetchall()
    return [_serialize_order(row) for row in rows]


@router.get("/orders/{order_number}")
def admin_order_detail(order_number: str, request: Request) -> dict:
    _authorize(request, "orders", "read")
    with get_connection() as connection:
        if order_number.isdecimal():
            sub_order = connection.execute(
                """
                SELECT so.id, so.parent_order_id, so.seller_id, so.items_json,
                       so.subtotal, so.commission_amount, so.seller_payout_amount,
                       so.fulfillment_status, so.admin_override_status,
                       so.courier_name, so.tracking_number, so.updated_at,
                       s.store_name, o.order_number, o.tracking_id,
                       o.customer_name, o.customer_phone, o.delivery_address,
                       o.payment_status, o.total_cents, o.shipping_cents,
                       o.created_at
                FROM sub_orders so
                JOIN sellers s ON s.id = so.seller_id
                JOIN orders o ON o.id = so.parent_order_id
                WHERE so.id = ?
                """,
                (int(order_number),),
            ).fetchone()
            if sub_order is not None:
                return _serialize_fulfillment_order(connection, sub_order)
        row = connection.execute(
            "SELECT * FROM orders WHERE order_number = ?", (order_number,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        items = connection.execute(
            """
            SELECT product_id, product_name, unit_price_cents, quantity, variant
            FROM order_items WHERE order_id = ? ORDER BY id
            """,
            (row["id"],),
        ).fetchall()
    return _serialize_order(
        row,
        [
            {
                "product_id": item["product_id"],
                "name": item["product_name"],
                "price": item["unit_price_cents"] / 100,
                "quantity": item["quantity"],
                "variant": item["variant"],
                "line_total": item["unit_price_cents"] * item["quantity"] / 100,
            }
            for item in items
        ],
    )


@router.put("/orders/{order_id}/override-status")
def override_marketplace_order_status(
    order_id: int,
    update: AdminOrderOverrideUpdate,
    request: Request,
) -> dict:
    username = _authorize(request, "orders", "write")
    _verify_admin_write(request)
    canonical_status = {
        "PENDING_PACKING": "PENDING",
        "PACKED": "PROCESSING",
        "DISPATCHED_TO_COURIER": "SHIPPED",
        "OUT_FOR_DELIVERY": "SHIPPED",
        "DELIVERED": "DELIVERED",
    }.get(update.status)
    with get_connection() as connection:
        sub_order = connection.execute(
            """
            SELECT id, parent_order_id
            FROM sub_orders WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if sub_order is None:
            raise HTTPException(status_code=404, detail="Seller order was not found.")
        connection.execute(
            """
            UPDATE sub_orders
            SET fulfillment_status = COALESCE(?, fulfillment_status),
                admin_override_status = ?,
                courier_name = CASE WHEN ? = '' THEN courier_name ELSE ? END,
                tracking_number = CASE WHEN ? = '' THEN tracking_number ELSE ? END,
                dispatched_at = CASE
                    WHEN ? IN ('DISPATCHED_TO_COURIER', 'OUT_FOR_DELIVERY')
                    THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ELSE dispatched_at
                END,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (
                canonical_status,
                update.status,
                update.courier_name,
                update.courier_name,
                update.tracking_number,
                update.tracking_number,
                update.status,
                order_id,
            ),
        )
        record_order_status_event(
            connection,
            sub_order["parent_order_id"],
            order_id,
            update.status,
            f"admin:{username}",
            update.note,
        )
        connection.execute(
            "UPDATE orders SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (sub_order["parent_order_id"],),
        )
        _audit(
            connection,
            request,
            "orders",
            "FULFILLMENT_OVERRIDE",
            f"Admin overrode seller order {order_id} to {update.status}.",
            severity="WARNING",
            details={
                "sub_order_id": order_id,
                "status": update.status,
                "courier_name": update.courier_name,
                "tracking_number": update.tracking_number,
                "note": update.note,
            },
        )
        connection.commit()
    publish_order_update(
        request, sub_order["parent_order_id"], order_id, update.status
    )
    return {
        "id": order_id,
        "fulfillment_status": update.status,
        "courier_name": update.courier_name,
        "tracking_number": update.tracking_number,
    }


@router.patch("/orders/{order_number}/status")
def update_order_status(
    order_number: str, payload: OrderStatusUpdate, request: Request
) -> dict:
    _authorize(request, "orders", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        before = connection.execute(
            "SELECT status FROM orders WHERE order_number = ?", (order_number,)
        ).fetchone()
        if before is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        cursor = connection.execute(
            "UPDATE orders SET status = ? WHERE order_number = ?",
            (payload.status, order_number),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order not found.")
        _audit(
            connection,
            request,
            "Orders",
            "ORDER_STATUS_UPDATED",
            f"Changed order {order_number} from {before['status']} to {payload.status}.",
            details={
                "order_number": order_number,
                "before": before["status"],
                "after": payload.status,
            },
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM orders WHERE order_number = ?", (order_number,)
        ).fetchone()
    return _serialize_order(row)


@router.get("/customers")
def admin_customers(request: Request, search: str = Query(default="", max_length=100)) -> list[dict]:
    _authorize(request, "orders", "read")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT customer_name, customer_phone, delivery_address,
                   COUNT(*) AS order_count,
                   SUM(CASE WHEN status != 'cancelled' THEN total_cents ELSE 0 END) AS spend_cents,
                   MAX(created_at) AS last_order
            FROM orders
            GROUP BY customer_phone, customer_name, delivery_address
            ORDER BY last_order DESC
            """
        ).fetchall()
    customers = [
        {
            "name": row["customer_name"],
            "phone": row["customer_phone"],
            "address": row["delivery_address"],
            "order_count": row["order_count"],
            "total_spend": row["spend_cents"] / 100,
            "last_order": row["last_order"],
        }
        for row in rows
    ]
    query = search.strip().casefold()
    if query:
        customers = [
            customer
            for customer in customers
            if query in customer["name"].casefold()
            or query in customer["phone"].casefold()
        ]
    return customers


@router.get("/notifications")
def admin_notifications(request: Request) -> dict:
    _authorize(request, "orders", "read")
    with get_connection() as connection:
        low_stock = connection.execute(
            """
            SELECT id, name, stock, low_stock_threshold
            FROM products WHERE active = 1 AND stock <= low_stock_threshold
            ORDER BY stock, name LIMIT 10
            """
        ).fetchall()
        new_orders = connection.execute(
            """
            SELECT order_number, customer_name, total_cents, created_at
            FROM orders WHERE created_at >= datetime('now', '-1 day')
            ORDER BY created_at DESC LIMIT 10
            """
        ).fetchall()
    return {
        "low_stock": [dict(row) for row in low_stock],
        "new_orders": [
            {
                "order_number": row["order_number"],
                "customer_name": row["customer_name"],
                "total": row["total_cents"] / 100,
                "created_at": row["created_at"],
            }
            for row in new_orders
        ],
    }


@router.get("/campaigns")
def admin_campaigns(request: Request) -> list[dict]:
    _authorize(request, "settings", "read")
    with get_connection() as connection:
        connection.execute(
            "UPDATE campaigns SET active = 0 WHERE active = 1 AND ends_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()
        rows = connection.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignInput, request: Request) -> dict:
    _authorize(request, "settings", "write")
    _verify_admin_write(request)
    starts = datetime.now(timezone.utc)
    ends = starts + timedelta(minutes=payload.duration_minutes)
    with get_connection() as connection:
        connection.execute("UPDATE campaigns SET active = 0 WHERE active = 1")
        cursor = connection.execute(
            """
            INSERT INTO campaigns (
                title, discount_percent, stock_allocation, duration_minutes,
                starts_at, ends_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                payload.title,
                payload.discount_percent,
                payload.stock_allocation,
                payload.duration_minutes,
                starts.isoformat(),
                ends.isoformat(),
            ),
        )
        _audit(
            connection,
            request,
            "System",
            "CAMPAIGN_CREATED",
            f"Launched campaign {payload.title} with {payload.discount_percent}% discount.",
            details={
                "campaign_id": cursor.lastrowid,
                "duration_minutes": payload.duration_minutes,
            },
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM campaigns WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@router.delete("/campaigns/{campaign_id}")
def deactivate_campaign(campaign_id: int, request: Request) -> dict[str, str]:
    _authorize(request, "settings", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE campaigns SET active = 0 WHERE id = ?", (campaign_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Campaign not found.")
        _audit(
            connection,
            request,
            "System",
            "CAMPAIGN_ENDED",
            f"Ended promotion campaign #{campaign_id}.",
            details={"campaign_id": campaign_id},
        )
        connection.commit()
    return {"message": "Campaign ended."}


@router.get("/settings")
def admin_settings(request: Request) -> dict:
    _authorize(request, "settings", "read")
    with get_connection() as connection:
        connection.execute(
            "UPDATE campaigns SET active = 0 WHERE active = 1 AND ends_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()
        row = connection.execute(
            "SELECT value FROM store_settings WHERE key = 'store_status'"
        ).fetchone()
        campaign_count = connection.execute(
            "SELECT COUNT(*) FROM campaigns WHERE active = 1"
        ).fetchone()[0]
    return {
        "store_status": row["value"] if row else "live",
        "currency": "KES",
        "timezone": "Africa/Nairobi",
        "campaigns_active": campaign_count,
        "admin_username": current_admin(request),
    }


@router.put("/settings")
def update_admin_settings(
    payload: StoreSettingsUpdate, request: Request
) -> dict:
    _authorize(request, "settings", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        previous = connection.execute(
            "SELECT value FROM store_settings WHERE key = 'store_status'"
        ).fetchone()
        connection.execute(
            """
            INSERT INTO store_settings (key, value) VALUES ('store_status', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (payload.store_status,),
        )
        _audit(
            connection,
            request,
            "System",
            "STORE_STATUS_UPDATED",
            f"Changed storefront status to {payload.store_status}.",
            details={
                "before": previous["value"] if previous else "live",
                "after": payload.store_status,
            },
        )
        connection.commit()
    return {"store_status": payload.store_status, "currency": "KES"}


@router.get("/security/sessions")
def admin_active_sessions(request: Request) -> list[dict]:
    _authorize(request, "settings", "read")
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=8 * 60 * 60)).isoformat()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT session_id, username, role, ip_address, user_agent,
                   created_at, last_active_at
            FROM admin_sessions
            WHERE revoked_at IS NULL AND created_at >= ?
            ORDER BY last_active_at DESC
            """,
            (cutoff,),
        ).fetchall()
    sessions = []
    for row in rows:
        agent = row["user_agent"].casefold()
        device = (
            "Mobile"
            if any(token in agent for token in ("mobile", "android", "iphone"))
            else "Tablet"
            if "ipad" in agent or "tablet" in agent
            else "Desktop"
        )
        sessions.append({**dict(row), "device_type": device})
    return sessions


@router.delete("/security/sessions/{session_id}")
def revoke_admin_session(session_id: str, request: Request) -> dict[str, str]:
    _authorize(request, "settings", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE admin_sessions SET revoked_at = ?
            WHERE session_id = ? AND revoked_at IS NULL
            """,
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Active session not found.")
        _audit(
            connection,
            request,
            "Auth",
            "SESSION_REVOKED",
            f"Revoked administrator session {session_id}.",
            "WARNING",
            {"session_id": session_id},
        )
        connection.commit()
    return {"message": "Session revoked."}


@router.get("/security/roles")
def admin_role_permissions(request: Request) -> list[dict]:
    _authorize(request, "settings", "read")
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT role, permissions_json FROM admin_role_permissions ORDER BY role"
        ).fetchall()
    return [
        {"role": row["role"], "permissions": json.loads(row["permissions_json"])}
        for row in rows
    ]


@router.put("/security/roles/{role}")
def update_admin_role(
    role: str, payload: RolePermissionsUpdate, request: Request
) -> dict:
    _authorize(request, "settings", "write")
    _verify_admin_write(request)
    if role not in {
        "Super Admin",
        "Store Manager",
        "Support Agent",
        "Inventory Clerk",
    }:
        raise HTTPException(status_code=404, detail="Admin role not found.")
    if role == "Super Admin" and any(
        not permission
        for rights in payload.permissions.values()
        for permission in rights.values()
    ):
        raise HTTPException(
            status_code=422,
            detail="Super Admin must retain every permission to prevent lockout.",
        )
    serialized = json.dumps(payload.permissions, sort_keys=True)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_role_permissions (role, permissions_json)
            VALUES (?, ?)
            ON CONFLICT(role) DO UPDATE SET permissions_json = excluded.permissions_json
            """,
            (role, serialized),
        )
        _audit(
            connection,
            request,
            "System",
            "ROLE_PERMISSIONS_UPDATED",
            f"Updated permission matrix for role {role}.",
            "WARNING",
            {"role": role, "permissions": payload.permissions},
        )
        connection.commit()
    return {"role": role, "permissions": payload.permissions}


@router.get("/security/alerts")
def admin_security_alerts(request: Request) -> dict:
    _authorize(request, "settings", "read")
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with get_connection() as connection:
        failures = connection.execute(
            """
            SELECT ip_address, COUNT(*) AS attempts, MAX(created_at) AS latest
            FROM admin_login_attempts
            WHERE succeeded = 0 AND created_at >= ?
            GROUP BY ip_address
            ORDER BY attempts DESC, latest DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()
        recent_events = connection.execute(
            """
            SELECT id, occurred_at, admin_username, event_type, description,
                   ip_address, severity, event_category
            FROM admin_audit_logs
            WHERE severity IN ('WARNING', 'CRITICAL') AND occurred_at >= ?
            ORDER BY occurred_at DESC LIMIT 20
            """,
            (cutoff,),
        ).fetchall()
    return {
        "failed_logins": [
            {
                **dict(row),
                "message": f"{row['attempts']} failed admin login attempt(s) from {row['ip_address']}.",
                "severity": "CRITICAL" if row["attempts"] >= 3 else "WARNING",
            }
            for row in failures
        ],
        "events": [dict(row) for row in recent_events],
    }


@router.get("/audit-logs")
def admin_audit_logs(
    request: Request,
    category: str = Query(default="all", max_length=20),
    search: str = Query(default="", max_length=120),
    start_date: str = Query(default="", max_length=10),
    end_date: str = Query(default="", max_length=10),
    limit: int = Query(default=200, ge=1, le=1000),
    export: str = Query(default="", pattern="^(|csv|json)$"),
):
    _authorize(request, "settings", "read")
    allowed_categories = {"Auth", "Inventory", "Orders", "Pricing", "System"}
    if category != "all" and category not in allowed_categories:
        raise HTTPException(status_code=422, detail="Unknown audit category.")
    for supplied_date in (start_date, end_date):
        if supplied_date:
            try:
                datetime.strptime(supplied_date, "%Y-%m-%d")
            except ValueError as error:
                raise HTTPException(
                    status_code=422, detail="Dates must use YYYY-MM-DD format."
                ) from error
    conditions = []
    parameters: list[object] = []
    if category != "all":
        conditions.append("event_category = ?")
        parameters.append(category)
    if start_date:
        conditions.append("occurred_at >= ?")
        parameters.append(f"{start_date}T00:00:00")
    if end_date:
        conditions.append("occurred_at < ?")
        parameters.append(
            (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime(
                "%Y-%m-%dT00:00:00"
            )
        )
    if search.strip():
        term = f"%{search.strip().casefold()}%"
        conditions.append(
            """
            (lower(admin_username) LIKE ? OR lower(event_type) LIKE ?
             OR lower(description) LIKE ? OR lower(ip_address) LIKE ?)
            """
        )
        parameters.extend([term, term, term, term])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    parameters.append(limit)
    with get_connection() as connection:
        rows = _audit_rows(
            connection,
            f"""
            SELECT id, occurred_at, admin_username, event_category, event_type,
                   description, ip_address, severity, details_json
            FROM admin_audit_logs {where_clause}
            ORDER BY occurred_at DESC, id DESC LIMIT ?
            """,
            tuple(parameters),
        )
    if export == "json":
        return Response(
            content=json.dumps(rows, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="maison-muse-audit.json"'},
        )
    if export == "csv":
        output = io.StringIO(newline="")
        fields = [
            "occurred_at",
            "admin_username",
            "event_category",
            "event_type",
            "description",
            "ip_address",
            "severity",
            "details",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = {}
            for field in fields:
                value = str(row.get(field, ""))
                if value.startswith(("=", "+", "-", "@", "\t", "\r")):
                    value = f"'{value}"
                values[field] = value
            writer.writerow(values)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="maison-muse-audit.csv"'},
        )
    return rows


@router.get("/payments")
def admin_payment_logs(
    request: Request, search: str = Query(default="", max_length=100)
) -> dict:
    _authorize(request, "orders", "read")
    term = f"%{search.strip().casefold()}%"
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, order_number, payment_method, payment_gateway,
                   gateway_reference, gateway_tracking_id, gateway_status,
                   payment_status,
                   total_cents, created_at
            FROM orders
            WHERE ? = '%%' OR lower(order_number) LIKE ?
            ORDER BY created_at DESC LIMIT 200
            """,
            (term, term),
        ).fetchall()
    transactions = []
    for row in rows:
        payment_status = row["payment_status"]
        gateway_status = {
            "paid": "matched",
            "failed": "payment_failed",
            "reversed": "refunded",
            "refunded": "refunded",
            "pending_callback": "pending_callback",
            "processing": "processing",
        }.get(payment_status, "not_processed")
        transactions.append(
            {
                "order_id": row["order_number"],
                "internal_order_id": row["id"],
                "gateway": row["payment_gateway"] or (
                    "M-Pesa / Mobile Money"
                    if row["payment_method"] == "mobile-money"
                    else "Card"
                ),
                "gateway_reference": row["gateway_reference"] or None,
                "gateway_tracking_id": row["gateway_tracking_id"] or None,
                "provider_status": row["gateway_status"],
                "amount": row["total_cents"] / 100,
                "gateway_status": gateway_status,
                "payment_status": payment_status,
                "created_at": row["created_at"],
            }
        )
    gateway_configured = is_configured()
    return {
        "gateway_configured": gateway_configured,
        "transactions": transactions,
        "notice": (
            "Pesapal is not fully configured. Complete the backend Pesapal environment setup "
            "before accepting payments."
            if not gateway_configured
            else ""
        ),
    }


@router.post("/payments/{order_number}/reconcile")
def reconcile_payment(order_number: str, request: Request) -> dict:
    _authorize(request, "orders", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        order = connection.execute(
            """
            SELECT payment_status, gateway_tracking_id
            FROM orders WHERE order_number = ?
            """,
            (order_number,),
        ).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        if not order["gateway_tracking_id"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This order has no Pesapal transaction to reconcile.",
            )
        tracking_id = order["gateway_tracking_id"]

    payment = refresh_order_payment(order_number, tracking_id)
    with get_connection() as connection:
        _audit(
            connection,
            request,
            "Orders",
            "PESAPAL_PAYMENT_RECONCILED",
            f"Reconciled Pesapal payment for {order_number}.",
            "INFO",
            {
                "order_number": order_number,
                "payment_status": payment["payment_status"],
                "provider_status": payment["provider_status"],
            },
        )
        connection.commit()
    return payment


@router.get("/customer-insights")
def admin_customer_insights(request: Request) -> dict:
    _authorize(request, "orders", "read")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, order_number, customer_name, customer_phone, total_cents,
                   payment_attempts, payment_status, created_at
            FROM orders WHERE status != 'cancelled'
            ORDER BY created_at DESC LIMIT 200
            """
        ).fetchall()
    risk_orders = []
    for row in rows:
        high_value = row["total_cents"] >= 1_000_000
        repeated_failures = row["payment_attempts"] >= 3
        score = min(100, (40 if high_value else 0) + (60 if repeated_failures else 0))
        if score >= 40:
            risk_orders.append(
                {
                    "order_number": row["order_number"],
                    "customer_name": row["customer_name"],
                    "customer_phone": row["customer_phone"],
                    "amount": row["total_cents"] / 100,
                    "payment_attempts": row["payment_attempts"],
                    "payment_status": row["payment_status"],
                    "risk_score": score,
                    "reasons": [
                        reason
                        for flagged, reason in (
                            (high_value, "High-value order"),
                            (repeated_failures, "Three or more failed payment attempts"),
                        )
                        if flagged
                    ],
                    "created_at": row["created_at"],
                }
            )
    return {
        "abandoned_carts": [],
        "cart_capture_enabled": False,
        "cart_notice": "Abandoned checkout capture is not enabled. The storefront does not persist customer contact details before order submission.",
        "risk_orders": risk_orders,
        "risk_notice": "Risk scores are triage signals only, not fraud determinations. Payment-attempt counts remain zero until a gateway is integrated.",
    }


@router.get("/suppliers/overview")
def supplier_overview(request: Request) -> dict:
    _authorize(request, "products", "read")
    with get_connection() as connection:
        categories = connection.execute(
            """
            SELECT category, COUNT(*) AS products,
                   SUM(CASE WHEN unit_cost > 0 THEN 1 ELSE 0 END) AS costed_products,
                   SUM(CASE WHEN unit_cost > 0 THEN (price - unit_cost) ELSE 0 END) AS gross_profit,
                   SUM(CASE WHEN unit_cost > 0 THEN price ELSE 0 END) AS revenue
            FROM products WHERE active = 1 GROUP BY category ORDER BY category
            """
        ).fetchall()
        low_stock = connection.execute(
            """
            SELECT id, name, category, price, unit_cost, stock, low_stock_threshold
            FROM products
            WHERE active = 1 AND stock <= low_stock_threshold
            ORDER BY stock, name
            """
        ).fetchall()
        purchase_orders = connection.execute(
            "SELECT * FROM purchase_orders ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    margins = []
    for row in categories:
        margins.append(
            {
                "category": row["category"],
                "products": row["products"],
                "costed_products": row["costed_products"],
                "gross_margin_percent": (
                    round(row["gross_profit"] / row["revenue"] * 100, 1)
                    if row["revenue"]
                    else None
                ),
            }
        )
    return {
        "categories": margins,
        "low_stock": [dict(row) for row in low_stock],
        "purchase_orders": [dict(row) for row in purchase_orders],
    }


@router.patch("/products/{product_id}/cost")
def update_product_cost(
    product_id: str, payload: ProductCostUpdate, request: Request
) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    with get_connection() as connection:
        before = connection.execute(
            "SELECT name, unit_cost FROM products WHERE id = ? AND active = 1",
            (product_id,),
        ).fetchone()
        if before is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        connection.execute(
            "UPDATE products SET unit_cost = ? WHERE id = ?",
            (payload.unit_cost, product_id),
        )
        _audit(
            connection,
            request,
            "Pricing",
            "PRODUCT_COST_UPDATED",
            f"Updated cost of goods for {before['name']} from {before['unit_cost']} to {payload.unit_cost}.",
            details={
                "product_id": product_id,
                "before": before["unit_cost"],
                "after": payload.unit_cost,
            },
        )
        connection.commit()
    return {"product_id": product_id, "unit_cost": payload.unit_cost}


@router.get("/suppliers/purchase-orders")
def list_purchase_orders(request: Request) -> list[dict]:
    _authorize(request, "products", "read")
    with get_connection() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM purchase_orders ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        ]


@router.post("/suppliers/purchase-orders/draft-low-stock")
def draft_low_stock_purchase_orders(request: Request) -> dict:
    _authorize(request, "products", "write")
    _verify_admin_write(request)
    now = datetime.now(timezone.utc).isoformat()
    created = []
    with get_connection() as connection:
        products = connection.execute(
            """
            SELECT id, name, stock, low_stock_threshold, unit_cost
            FROM products WHERE active = 1 AND stock <= low_stock_threshold
            ORDER BY stock, name
            """
        ).fetchall()
        skipped_missing_cost = 0
        existing_drafts = {
            row["product_id"]
            for row in connection.execute(
                "SELECT product_id FROM purchase_orders WHERE status = 'draft'"
            ).fetchall()
        }
        for product in products:
            if product["unit_cost"] <= 0:
                skipped_missing_cost += 1
                continue
            if product["id"] in existing_drafts:
                continue
            quantity = max(1, product["low_stock_threshold"] * 3 - product["stock"])
            total_cost = round(product["unit_cost"] * quantity, 2)
            cursor = connection.execute(
                """
                INSERT INTO purchase_orders (
                    product_id, product_name, quantity, unit_cost, total_cost,
                    status, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
                """,
                (
                    product["id"],
                    product["name"],
                    quantity,
                    product["unit_cost"],
                    total_cost,
                    request.state.admin_identity["username"],
                    now,
                ),
            )
            created.append(
                {
                    "id": cursor.lastrowid,
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity": quantity,
                    "unit_cost": product["unit_cost"],
                    "total_cost": total_cost,
                    "status": "draft",
                }
            )
        if created:
            _audit(
                connection,
                request,
                "Inventory",
                "PURCHASE_ORDERS_DRAFTED",
                f"Generated {len(created)} draft purchase order(s) for low-stock products.",
                details={"purchase_orders": created},
            )
        connection.commit()
    return {"created": created, "skipped_missing_cost": skipped_missing_cost}


@router.get("/seller-qc")
def list_seller_product_qc_queue(request: Request) -> list[dict]:
    _authorize(request, "products", "read")
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT p.id, p.name, p.brand, p.sku, p.category, p.image,
                      p.qc_status, p.product_status, s.id AS seller_id,
                      s.store_name, s.store_slug, q.notes, q.created_at AS submitted_at
               FROM products p
               JOIN sellers s ON s.id = p.seller_id
               LEFT JOIN seller_qc_audits q ON q.id = (
                   SELECT MAX(latest.id) FROM seller_qc_audits latest
                   WHERE latest.product_id = p.id AND latest.seller_id = s.id
               )
               WHERE p.qc_status = 'PENDING_QC'
               ORDER BY q.created_at, p.name"""
        ).fetchall()
    return [dict(row) for row in rows]


@router.post("/seller-qc/{product_id}")
def decide_seller_product_qc(
    product_id: str, review: SellerQcReviewUpdate, request: Request
) -> dict:
    username = _authorize(request, "products", "write")
    _verify_admin_write(request)
    qc_status = (
        "APPROVED_LIVE" if review.action == "APPROVE" else "REJECTED_IMAGE_QUALITY"
    )
    with get_connection() as connection:
        product = connection.execute(
            "SELECT id, seller_id, qc_status FROM products WHERE id = ? AND seller_id IS NOT NULL",
            (product_id,),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Seller product was not found.")
        if product["qc_status"] != "PENDING_QC":
            raise HTTPException(
                status_code=409, detail="This product is not waiting for QC review."
            )
        connection.execute(
            """UPDATE products SET qc_status = ?, product_status = ?, active = ?
               WHERE id = ?""",
            (
                qc_status,
                "ACTIVE" if review.action == "APPROVE" else "DRAFT",
                1 if review.action == "APPROVE" else 0,
                product_id,
            ),
        )
        connection.execute(
            """INSERT INTO seller_qc_audits
               (seller_id, product_id, qc_status, notes, reviewed_by)
               VALUES (?, ?, ?, ?, ?)""",
            (product["seller_id"], product_id, qc_status, review.notes, username),
        )
        _audit(
            connection,
            request,
            "Marketplace",
            f"SELLER_PRODUCT_QC_{review.action}",
            f"{review.action.title()} quality review for seller product {product_id}.",
            details={
                "product_id": product_id,
                "seller_id": product["seller_id"],
                "qc_status": qc_status,
                "notes": review.notes,
            },
        )
        connection.commit()
    return {"product_id": product_id, "qc_status": qc_status}


@router.get("/storefront/status")
def public_storefront_status() -> dict:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM store_settings WHERE key = 'store_status'"
        ).fetchone()
    return {"store_status": row["value"] if row else "live"}


__all__ = ["router", "ADMIN_COOKIE_NAME"]
