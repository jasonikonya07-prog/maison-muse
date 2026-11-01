import csv
import hashlib
import io
import json
import re
import secrets
import sqlite3
from zipfile import BadZipFile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.database import get_connection
from app.routers.products import expire_seller_promotions
from app.routers.sellers import (
    _seller_product_payload,
    _verify_seller_write,
    require_seller,
)
from app.schemas import (
    SellerAdBoostInput,
    SellerBranchCreate,
    SellerBranchInventoryUpdate,
    SellerBuyerMessage,
    SellerBuyerReply,
    SellerCampaignEnrollment,
    SellerDropoffManifestInput,
    SellerFulfillmentModeUpdate,
    SellerMessageReply,
    SellerNotificationPreferences,
    SellerProductInput,
    SellerPromotionInput,
    SellerRepricingRuleInput,
    SellerRestockRecommendationInput,
    SellerReviewRequestInput,
    SellerReturnCreate,
    SellerReturnRequest,
    SellerTeamInvite,
    SellerTeamMemberStatus,
    SellerVasRequest,
)


router = APIRouter()


def _available_balance(connection, seller_id: int) -> float:
    ledger_balance = connection.execute(
        """
        SELECT COALESCE(SUM(
            COALESCE(ledger.net_amount, so.seller_payout_amount)
            - COALESCE(ledger.paid_amount, 0)
        ), 0)
        FROM sub_orders so
        JOIN orders o ON o.id = so.parent_order_id
        LEFT JOIN seller_payout_ledger ledger ON ledger.sub_order_id = so.id
        LEFT JOIN payout_allocations pa ON pa.sub_order_id = so.id
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
        (seller_id,),
    ).fetchone()[0]
    ad_spend = connection.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM seller_ad_transactions
        WHERE seller_id = ? AND status = 'COMPLETED'
        """,
        (seller_id,),
    ).fetchone()[0]
    return round(max(0, ledger_balance - ad_spend), 2)


def _promotion_payload(row, product_names: list[str] | None = None) -> dict:
    return {
        "id": row["id"],
        "type": row["promotion_type"],
        "name": row["name"],
        "code": row["code"] or "",
        "discount_percent": row["discount_percent"],
        "usage_limit": row["usage_limit"],
        "usage_count": row["usage_count"],
        "starts_at": row["starts_at"],
        "expires_at": row["expires_at"],
        "status": row["status"],
        "product_ids": json.loads(row["product_ids_json"] or "[]"),
        "product_names": product_names or [],
    }


@router.get("/seller/health")
def seller_health(request: Request) -> dict:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        orders = connection.execute(
            """
            SELECT COUNT(*) AS order_count,
                   SUM(CASE WHEN lower(o.status) = 'cancelled'
                       OR lower(o.payment_status) = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
                   SUM(CASE WHEN so.dispatched_at != '' THEN 1 ELSE 0 END) AS dispatched,
                   SUM(CASE WHEN so.dispatched_at != ''
                         AND julianday(so.dispatched_at) - julianday(so.created_at) <= 1
                       THEN 1 ELSE 0 END) AS on_time
            FROM sub_orders so
            JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ?
            """,
            (seller["id"],),
        ).fetchone()
        returns = connection.execute(
            "SELECT COUNT(*) FROM seller_returns WHERE seller_id = ?",
            (seller["id"],),
        ).fetchone()[0]
        rating = float(seller["rating"] or 0)
        order_count = orders["order_count"] or 0
        dispatched = orders["dispatched"] or 0
        on_time_rate = (orders["on_time"] or 0) / dispatched * 100 if dispatched else 0
        cancellation_rate = (orders["cancelled"] or 0) / order_count * 100 if order_count else 0
        return_rate = returns / order_count * 100 if order_count else 0
    badges = []
    if rating >= 4.8:
        badges.append("Top Rated Seller")
    if dispatched and on_time_rate >= 95:
        badges.append("Express Shipper")
    if (
        order_count >= 10
        and rating >= 4.8
        and on_time_rate >= 95
        and cancellation_rate < 1
        and return_rate < 2
    ):
        badges.append("Maison Elite Vendor")
    return {
        "cancellation_rate": round(cancellation_rate, 2),
        "on_time_dispatch_rate": round(on_time_rate, 2),
        "average_rating": round(rating, 2),
        "return_dispute_rate": round(return_rate, 2),
        "orders_reviewed": order_count,
        "badges": badges,
        "targets": {
            "cancellation_rate_percent": 1,
            "dispatch_hours": 24,
            "rating": 4.8,
            "return_dispute_rate_percent": 2,
        },
    }


@router.get("/seller/promotions")
def list_seller_promotions(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM seller_promotions
            WHERE seller_id = ? ORDER BY created_at DESC, id DESC
            """,
            (seller["id"],),
        ).fetchall()
        results = []
        for row in rows:
            ids = json.loads(row["product_ids_json"] or "[]")
            names = []
            if ids:
                placeholders = ",".join("?" for _ in ids)
                names = [
                    product["name"]
                    for product in connection.execute(
                        f"SELECT name FROM products WHERE seller_id = ? AND id IN ({placeholders}) ORDER BY name",
                        [seller["id"], *ids],
                    ).fetchall()
                ]
            results.append(_promotion_payload(row, names))
    return results


@router.post("/promotions", status_code=status.HTTP_201_CREATED)
def create_seller_promotion(
    promotion: SellerPromotionInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        expire_seller_promotions(connection)
        products = connection.execute(
            f"""
            SELECT id, name, price FROM products
            WHERE seller_id = ? AND active = 1
              AND id IN ({','.join('?' for _ in promotion.product_ids)})
            """,
            [seller["id"], *promotion.product_ids],
        ).fetchall()
        if len(products) != len(promotion.product_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more selected products are unavailable in your catalog.",
            )
        if promotion.promotion_type in {"flash_sale", "price_discount"}:
            active_promotions = connection.execute(
                """
                SELECT product_ids_json FROM seller_promotions
                WHERE seller_id = ? AND status = 'ACTIVE'
                  AND promotion_type IN ('flash_sale', 'price_discount')
                  AND expires_at > ?
                """,
                (seller["id"], datetime.now(timezone.utc).isoformat()),
            ).fetchall()
            occupied_ids = {
                product_id
                for active in active_promotions
                for product_id in json.loads(active["product_ids_json"] or "[]")
            }
            if occupied_ids.intersection(promotion.product_ids):
                raise HTTPException(
                    status_code=409,
                    detail="A selected product already has an active price promotion.",
                )
        ids_json = json.dumps(promotion.product_ids)
        starts_at = datetime.now(timezone.utc).isoformat()
        expires_at = promotion.expires_at.astimezone(timezone.utc).isoformat()
        code = promotion.code.upper() if promotion.code else None
        try:
            cursor = connection.execute(
                """
                INSERT INTO seller_promotions (
                    seller_id, product_id, product_ids_json, promotion_type,
                    name, code, discount_percent, usage_limit, starts_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seller["id"],
                    promotion.product_ids[0],
                    ids_json,
                    promotion.promotion_type,
                    promotion.name,
                    code,
                    promotion.discount_percent,
                    promotion.usage_limit,
                    starts_at,
                    expires_at,
                ),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise HTTPException(
                    status_code=409, detail="That coupon code is already in use."
                ) from error
            raise

        if promotion.promotion_type in {"flash_sale", "price_discount"}:
            for product in products:
                connection.execute(
                    """
                    UPDATE products
                    SET old_price = CASE
                            WHEN old_price IS NULL OR old_price = 0 THEN price
                            ELSE old_price
                        END,
                        price = ROUND(price * (1 - ? / 100.0), 2),
                        discount = ? || '% OFF'
                    WHERE id = ? AND seller_id = ?
                    """,
                    (
                        promotion.discount_percent,
                        promotion.discount_percent,
                        product["id"],
                        seller["id"],
                    ),
                )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM seller_promotions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _promotion_payload(row, [product["name"] for product in products])


@router.get("/seller/campaigns")
def list_seller_campaigns(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, discount_percent, stock_allocation, starts_at, ends_at
            FROM campaigns
            WHERE active = 1 AND starts_at <= ? AND ends_at > ?
            ORDER BY starts_at
            """,
            (now, now),
        ).fetchall()
        enrollments = {
            row["campaign_id"]: json.loads(row["product_ids_json"])
            for row in connection.execute(
                """
                SELECT campaign_id, product_ids_json
                FROM seller_campaign_enrollments
                WHERE seller_id = ? AND status = 'ACTIVE'
                """,
                (seller["id"],),
            ).fetchall()
        }
    return [
        {
            **dict(row),
            "enrolled": row["id"] in enrollments,
            "product_ids": enrollments.get(row["id"], []),
        }
        for row in rows
    ]


@router.post("/seller/campaigns/{campaign_id}/enroll")
def enroll_seller_campaign(
    campaign_id: int,
    enrollment: SellerCampaignEnrollment,
    request: Request,
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        campaign = connection.execute(
            """
            SELECT id FROM campaigns
            WHERE id = ? AND active = 1 AND starts_at <= ? AND ends_at > ?
            """,
            (campaign_id, now, now),
        ).fetchone()
        if campaign is None:
            raise HTTPException(status_code=404, detail="This campaign is no longer open.")
        products = connection.execute(
            f"""
            SELECT id FROM products
            WHERE seller_id = ? AND active = 1 AND product_status = 'ACTIVE'
              AND stock > 0 AND id IN ({','.join('?' for _ in enrollment.product_ids)})
            """,
            [seller["id"], *enrollment.product_ids],
        ).fetchall()
        if len(products) != len(enrollment.product_ids):
            raise HTTPException(
                status_code=404,
                detail="Every selected product must be active, in stock, and belong to your store.",
            )
        connection.execute(
            """
            INSERT INTO seller_campaign_enrollments (
                campaign_id, seller_id, product_ids_json, status
            ) VALUES (?, ?, ?, 'ACTIVE')
            ON CONFLICT(campaign_id, seller_id) DO UPDATE SET
                product_ids_json = excluded.product_ids_json,
                status = 'ACTIVE'
            """,
            (campaign_id, seller["id"], json.dumps(enrollment.product_ids)),
        )
        connection.commit()
    return {
        "campaign_id": campaign_id,
        "product_ids": enrollment.product_ids,
        "status": "ACTIVE",
    }


@router.get("/seller/ads")
def list_seller_ads(request: Request) -> dict:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT a.id, a.product_id, p.name AS product_name, a.amount,
                   a.duration_days, a.reference, a.status, a.created_at,
                   p.boosted_until
            FROM seller_ad_transactions a
            JOIN products p ON p.id = a.product_id
            WHERE a.seller_id = ? ORDER BY a.created_at DESC
            """,
            (seller["id"],),
        ).fetchall()
        balance = _available_balance(connection, seller["id"])
    return {"items": [dict(row) for row in rows], "available_balance": balance}


@router.post("/products/boost", status_code=status.HTTP_201_CREATED)
def boost_seller_product(
    boost: SellerAdBoostInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(days=boost.duration_days)
    reference = f"DEMO-AD-{secrets.token_hex(5).upper()}"
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        product = connection.execute(
            """
            SELECT id, name FROM products
            WHERE id = ? AND seller_id = ? AND active = 1 AND product_status = 'ACTIVE'
            """,
            (boost.product_id, seller["id"]),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Choose one of your active products.")
        balance = _available_balance(connection, seller["id"])
        if boost.amount > balance:
            raise HTTPException(
                status_code=409,
                detail=f"Ad spend exceeds available escrow balance of KSh {balance:,.2f}.",
            )
        connection.execute(
            """
            INSERT INTO seller_ad_transactions (
                seller_id, product_id, amount, duration_days, reference
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                seller["id"],
                boost.product_id,
                boost.amount,
                boost.duration_days,
                reference,
            ),
        )
        connection.execute(
            "UPDATE products SET boosted_until = ?, tag = 'SPONSORED' WHERE id = ?",
            (ends_at.isoformat(), boost.product_id),
        )
        connection.commit()
        balance = _available_balance(connection, seller["id"])
    return {
        "reference": reference,
        "product_id": boost.product_id,
        "amount": boost.amount,
        "duration_days": boost.duration_days,
        "boosted_until": ends_at.isoformat(),
        "available_balance": balance,
        "status": "COMPLETED",
        "is_simulated": True,
    }


@router.get("/seller/returns")
def list_seller_returns(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT r.*, o.order_number, o.customer_name, o.customer_phone,
                   o.delivery_address, so.items_json
            FROM seller_returns r
            JOIN sub_orders so ON so.id = r.sub_order_id
            JOIN orders o ON o.id = so.parent_order_id
            WHERE r.seller_id = ? ORDER BY r.created_at DESC, r.id DESC
            """,
            (seller["id"],),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "sub_order_id": row["sub_order_id"],
            "order_number": row["order_number"],
            "customer": {
                "name": row["customer_name"],
                "phone": row["customer_phone"],
                "address": row["delivery_address"],
            },
            "items": json.loads(row["items_json"]),
            "reason": row["reason"],
            "status": row["status"],
            "evidence": row["evidence"],
            "resolution_note": row["resolution_note"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/returns", status_code=status.HTTP_201_CREATED)
def request_order_return(return_request: SellerReturnCreate) -> dict:
    with get_connection() as connection:
        order = connection.execute(
            """
            SELECT so.id, so.seller_id, so.fulfillment_status,
                   o.customer_phone, o.payment_status
            FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
            WHERE so.id = ? AND o.order_number = ?
            """,
            (return_request.sub_order_id, return_request.order_number),
        ).fetchone()
        if (
            order is None
            or re.sub(r"\D", "", order["customer_phone"])
            != re.sub(r"\D", "", return_request.customer_phone)
            or order["payment_status"] not in {"paid", "completed_demo"}
            or order["fulfillment_status"] != "DELIVERED"
        ):
            raise HTTPException(
                status_code=404, detail="The paid order could not be verified."
            )
        existing = connection.execute(
            "SELECT id FROM seller_returns WHERE sub_order_id = ? AND status = 'OPEN'",
            (return_request.sub_order_id,),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409, detail="A return request is already open for this order."
            )
        cursor = connection.execute(
            """
            INSERT INTO seller_returns (seller_id, sub_order_id, reason)
            VALUES (?, ?, ?)
            """,
            (order["seller_id"], order["id"], return_request.reason),
        )
        connection.commit()
    return {"id": cursor.lastrowid, "status": "OPEN"}


@router.put("/returns/{return_id}")
def update_seller_return(
    return_id: int, update: SellerReturnRequest, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    statuses = {
        "refund_approved": "REFUND_APPROVED",
        "replacement_offered": "REPLACEMENT_OFFERED",
        "escalated": "ESCALATED",
        "closed": "CLOSED",
    }
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE seller_returns
            SET status = ?, evidence = ?, resolution_note = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND seller_id = ? AND status IN ('OPEN', 'ESCALATED')
            """,
            (
                statuses[update.action],
                update.evidence,
                update.resolution_note,
                return_id,
                seller["id"],
            ),
        )
        if not cursor.rowcount:
            raise HTTPException(
                status_code=404, detail="Open return request not found."
            )
        connection.commit()
    return {"id": return_id, "status": statuses[update.action]}


@router.get("/seller/products/csv-template")
def seller_product_csv_template(request: Request) -> dict:
    require_seller(request, approved=True)
    return {
        "headers": [
            "name",
            "brand",
            "sku",
            "category",
            "detail",
            "description",
            "price",
            "stock",
            "images",
            "tags",
            "variants",
        ],
        "example": [
            "Velvet Press-On Nails",
            "Maison Demo",
            "MM-NAIL-001",
            "Beauty & Cosmetics",
            "Reusable salon-quality finish",
            "A reusable luxury nail set with multiple sizes.",
            "1800",
            "20",
            "https://images.example/main.jpg|https://images.example/detail.jpg",
            "nails|beauty|reusable",
            "Shape: Almond, Coffin; Length: Short, Medium",
        ],
    }


@router.post("/products/bulk-upload")
async def upload_seller_products_csv(
    request: Request, file: UploadFile = File(...)
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    file_name = (file.filename or "").casefold()
    is_xlsx = file_name.endswith(".xlsx") or file.content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    is_csv = file_name.endswith(".csv") or file.content_type in {
        "text/csv",
        "application/vnd.ms-excel",
        "application/csv",
    }
    if not is_xlsx and not is_csv:
        raise HTTPException(
            status_code=415, detail="Upload a UTF-8 CSV or Excel .xlsx product file."
        )
    content = await file.read(5 * 1024 * 1024 + 1)
    await file.close()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Catalog files must be 5 MB or smaller.")
    if is_xlsx:
        try:
            from openpyxl import load_workbook
            from openpyxl.utils.exceptions import InvalidFileException
        except ImportError as error:
            raise HTTPException(
                status_code=503,
                detail="Excel import support is unavailable. Install backend requirements and restart the API.",
            ) from error
        workbook = None
        try:
            workbook = load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
            worksheet = workbook.active
            if worksheet.max_row is None or worksheet.max_row < 2:
                raise HTTPException(
                    status_code=400, detail="The Excel sheet must include a header and product rows."
                )
            if worksheet.max_row > 501:
                raise HTTPException(
                    status_code=400, detail="Upload between 1 and 500 product rows."
                )
            headers = [
                str(value).strip() if value is not None else ""
                for value in next(
                    worksheet.iter_rows(min_row=1, max_row=1, values_only=True)
                )
            ]
            if not headers or any(not header for header in headers):
                raise HTTPException(status_code=400, detail="Excel header row is invalid.")
            if len(set(headers)) != len(headers):
                raise HTTPException(status_code=400, detail="Excel column names must be unique.")
            rows = []
            for row_number, values in enumerate(
                worksheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                if not any(value is not None and str(value).strip() for value in values):
                    continue
                rows.append(
                    (
                        row_number,
                        {
                            header: (
                                str(values[index]).strip()
                                if index < len(values) and values[index] is not None
                                else ""
                            )
                            for index, header in enumerate(headers)
                        },
                    )
                )
        except (InvalidFileException, BadZipFile, ValueError, OSError) as error:
            raise HTTPException(
                status_code=400, detail="Excel workbook is invalid or could not be read."
            ) from error
        finally:
            if workbook is not None:
                workbook.close()
    else:
        try:
            decoded = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded))
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from error
        if not reader.fieldnames or any(not header for header in reader.fieldnames):
            raise HTTPException(status_code=400, detail="CSV header row is invalid.")
        reader.fieldnames = [header.strip() for header in reader.fieldnames]
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise HTTPException(status_code=400, detail="CSV column names must be unique.")
        rows = list(enumerate(reader, start=2))
    required_headers = {
        "name",
        "brand",
        "sku",
        "category",
        "detail",
        "description",
        "price",
        "stock",
        "images",
    }
    if not required_headers.issubset(set(headers if is_xlsx else reader.fieldnames)):
        raise HTTPException(
            status_code=400,
            detail="Catalog is missing required columns. Download the seller product template.",
        )
    if not rows or len(rows) > 500:
        raise HTTPException(
            status_code=400, detail="Upload between 1 and 500 product rows."
        )
    created = 0
    errors = []
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for index, row in rows:
            try:
                variants = []
                for entry in (row.get("variants") or "").split(";"):
                    if not entry.strip():
                        continue
                    variant_name, separator, raw_options = entry.partition(":")
                    options = [value.strip() for value in raw_options.split(",") if value.strip()]
                    if not separator or not variant_name.strip() or not options:
                        raise ValueError("Variants must look like Size: 30ml, 50ml.")
                    variants.append({"name": variant_name.strip(), "options": options})
                product = SellerProductInput.model_validate(
                    {
                        "name": row.get("name", "").strip(),
                        "brand": row.get("brand", "").strip(),
                        "sku": row.get("sku", "").strip(),
                        "category": row.get("category", "").strip(),
                        "detail": row.get("detail", "").strip(),
                        "description": row.get("description", "").strip(),
                        "price": float(row.get("price", "")),
                        "stock": int(row.get("stock", "")),
                        "images": [
                            value.strip()
                            for value in row.get("images", "").split("|")
                            if value.strip()
                        ],
                        "tags": [
                            value.strip()
                            for value in (row.get("tags") or "").split("|")
                            if value.strip()
                        ],
                        "variants": variants,
                    }
                )
                values = _seller_product_payload(
                    product, seller, secrets.token_urlsafe(18)
                )
                values.update(
                    product_status="DRAFT",
                    active=0,
                    qc_status="PENDING_QC",
                )
                connection.execute("SAVEPOINT seller_product_import")
                try:
                    connection.execute(
                        """
                        INSERT INTO products (
                            id, name, brand, sku, category, detail, description,
                            price, stock, low_stock_threshold, image, gallery_json,
                            seller_id, tags_json, variants_json, product_status, active,
                            qc_status, is_agri_product, farmer_name, farmer_whatsapp,
                            seller_whatsapp_phone
                        ) VALUES (
                            :id, :name, :brand, :sku, :category, :detail, :description,
                            :price, :stock, :low_stock_threshold, :image, :gallery_json,
                            :seller_id, :tags_json, :variants_json, :product_status, :active,
                            :qc_status, :is_agri_product, :farmer_name, :farmer_whatsapp,
                            :seller_whatsapp_phone
                        )
                        """,
                        values,
                    )
                    connection.execute(
                        """INSERT INTO seller_qc_audits
                           (seller_id, product_id, qc_status, notes, reviewed_by)
                           VALUES (?, ?, 'PENDING_QC', 'Bulk listing submitted for review.', 'seller')""",
                        (seller["id"], values["id"]),
                    )
                    connection.execute("RELEASE SAVEPOINT seller_product_import")
                    created += 1
                except Exception:
                    connection.execute("ROLLBACK TO SAVEPOINT seller_product_import")
                    connection.execute("RELEASE SAVEPOINT seller_product_import")
                    raise
            except Exception as error:
                errors.append({"row": index, "message": str(error)[:300]})
        connection.commit()
    return {"created": created, "failed": len(errors), "errors": errors[:50]}


def _owned_product(connection, seller_id: int, product_id: str):
    row = connection.execute(
        "SELECT * FROM products WHERE id = ? AND seller_id = ?",
        (product_id, seller_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Your product was not found.")
    return row


@router.get("/seller/team")
def list_seller_team(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT id, email, full_name, role, permissions_json, status, created_at
               FROM seller_team_members WHERE seller_id = ? ORDER BY created_at DESC""",
            (seller["id"],),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "permissions": json.loads(row["permissions_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/seller/team", status_code=status.HTTP_201_CREATED)
def invite_seller_team_member(
    invitation: SellerTeamInvite, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    role_permissions = {
        "Inventory Clerk": ["catalog:read", "catalog:update_stock"],
        "Fulfillment Manager": [
            "orders:read",
            "orders:update_fulfillment",
            "messages:read",
            "messages:reply",
        ],
        "Accountant": ["ledger:read", "statements:read", "payouts:read"],
    }
    permissions = role_permissions[invitation.role]
    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """INSERT INTO seller_team_members
                   (seller_id, email, full_name, role, permissions_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    seller["id"],
                    invitation.email,
                    invitation.full_name,
                    invitation.role,
                    json.dumps(permissions),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="This email already has a team invitation."
            ) from error
        connection.commit()
        member_id = cursor.lastrowid
    return {
        "id": member_id,
        "email": invitation.email,
        "full_name": invitation.full_name,
        "role": invitation.role,
        "permissions": permissions,
        "status": "INVITED",
        "delivery_status": "NOT_SENT",
        "message": "Invitation saved. Email delivery is not configured.",
    }


@router.patch("/seller/team/{member_id}")
def update_seller_team_member(
    member_id: int, update: SellerTeamMemberStatus, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    if update.status != "REVOKED":
        raise HTTPException(
            status_code=409,
            detail="Team access can only be revoked here; activation requires verified invite acceptance.",
        )
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE seller_team_members SET status = 'REVOKED',
               updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE id = ? AND seller_id = ? AND status != 'REVOKED'""",
            (member_id, seller["id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="The team member was not found.")
        connection.commit()
    return {"id": member_id, "status": "REVOKED"}


@router.get("/seller/notifications")
def get_seller_notification_preferences(request: Request) -> dict:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM seller_notification_preferences WHERE seller_id = ?",
            (seller["id"],),
        ).fetchone()
    if row is None:
        return {
            "low_stock_sms": False,
            "low_stock_whatsapp": False,
            "incoming_orders_sms": False,
            "incoming_orders_whatsapp": False,
            "delivery_configured": False,
        }
    return {
        key: bool(row[key])
        for key in (
            "low_stock_sms",
            "low_stock_whatsapp",
            "incoming_orders_sms",
            "incoming_orders_whatsapp",
        )
    } | {"delivery_configured": False}


@router.put("/seller/notifications")
def update_seller_notification_preferences(
    preferences: SellerNotificationPreferences, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    values = preferences.model_dump()
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO seller_notification_preferences (
                   seller_id, low_stock_sms, low_stock_whatsapp,
                   incoming_orders_sms, incoming_orders_whatsapp
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(seller_id) DO UPDATE SET
                   low_stock_sms = excluded.low_stock_sms,
                   low_stock_whatsapp = excluded.low_stock_whatsapp,
                   incoming_orders_sms = excluded.incoming_orders_sms,
                   incoming_orders_whatsapp = excluded.incoming_orders_whatsapp,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (
                seller["id"],
                values["low_stock_sms"],
                values["low_stock_whatsapp"],
                values["incoming_orders_sms"],
                values["incoming_orders_whatsapp"],
            ),
        )
        connection.commit()
    return values | {
        "delivery_configured": False,
        "message": "Preferences saved; SMS and WhatsApp delivery is not configured.",
    }


@router.post("/messages", status_code=status.HTTP_201_CREATED)
def start_buyer_seller_conversation(
    message: SellerBuyerMessage, request: Request
) -> dict:
    product_id = message.product_id
    with get_connection() as connection:
        product = connection.execute(
            """SELECT id, seller_id FROM products
               WHERE id = ? AND seller_id IS NOT NULL AND active = 1
                 AND product_status = 'ACTIVE'""",
            (product_id,),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="The product was not found.")
        conversation_id = secrets.token_urlsafe(32)
        cursor = connection.execute(
            """INSERT INTO seller_messages (
                   conversation_id, seller_id, product_id, sender_role, sender_name, body
               ) VALUES (?, ?, ?, 'BUYER', ?, ?)""",
            (
                conversation_id,
                product["seller_id"],
                product_id,
                message.customer_name,
                message.body,
            ),
        )
        connection.commit()
    return {
        "conversation_id": conversation_id,
        "message_id": cursor.lastrowid,
        "status": "RECEIVED",
    }


@router.get("/seller/messages")
def list_seller_messages(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT m.id, m.conversation_id, m.product_id, p.name AS product_name,
                      m.sender_role, m.sender_name, m.body, m.read_at, m.created_at
               FROM seller_messages m
               LEFT JOIN products p ON p.id = m.product_id
               WHERE m.seller_id = ? ORDER BY m.id DESC LIMIT 500""",
            (seller["id"],),
        ).fetchall()
        connection.execute(
            """UPDATE seller_messages SET read_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE seller_id = ? AND sender_role = 'BUYER' AND read_at IS NULL""",
            (seller["id"],),
        )
        connection.commit()
    return [dict(row) for row in rows]


@router.get("/messages/{conversation_id}")
def get_buyer_conversation(conversation_id: str) -> list[dict]:
    if not 40 <= len(conversation_id) <= 80:
        raise HTTPException(status_code=404, detail="The conversation was not found.")
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT sender_role, sender_name, body, created_at
               FROM seller_messages WHERE conversation_id = ? ORDER BY id""",
            (conversation_id,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="The conversation was not found.")
    return [dict(row) for row in rows]


@router.post("/messages/{conversation_id}", status_code=status.HTTP_201_CREATED)
def reply_as_buyer(
    conversation_id: str, message: SellerBuyerReply
) -> dict:
    if not 40 <= len(conversation_id) <= 80:
        raise HTTPException(status_code=404, detail="The conversation was not found.")
    with get_connection() as connection:
        original = connection.execute(
            """SELECT seller_id, product_id, sender_name FROM seller_messages
               WHERE conversation_id = ? AND sender_role = 'BUYER'
               ORDER BY id LIMIT 1""",
            (conversation_id,),
        ).fetchone()
        if original is None:
            raise HTTPException(status_code=404, detail="The conversation was not found.")
        cursor = connection.execute(
            """INSERT INTO seller_messages (
                   conversation_id, seller_id, product_id, sender_role, sender_name, body
               ) VALUES (?, ?, ?, 'BUYER', ?, ?)""",
            (
                conversation_id,
                original["seller_id"],
                original["product_id"],
                original["sender_name"],
                message.body,
            ),
        )
        connection.commit()
    return {"message_id": cursor.lastrowid, "status": "RECEIVED"}


@router.post("/seller/messages/reply", status_code=status.HTTP_201_CREATED)
def reply_to_seller_message(reply: SellerMessageReply, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        conversation = connection.execute(
            """SELECT product_id FROM seller_messages
               WHERE seller_id = ? AND conversation_id = ? LIMIT 1""",
            (seller["id"], reply.conversation_id),
        ).fetchone()
        if conversation is None:
            raise HTTPException(status_code=404, detail="The conversation was not found.")
        cursor = connection.execute(
            """INSERT INTO seller_messages (
                   conversation_id, seller_id, product_id, sender_role, sender_name, body
               ) VALUES (?, ?, ?, 'SELLER', ?, ?)""",
            (
                reply.conversation_id,
                seller["id"],
                conversation["product_id"],
                seller["store_name"],
                reply.body,
            ),
        )
        connection.commit()
    return {"message_id": cursor.lastrowid, "delivery_status": "STORED"}


@router.get("/seller/fulfillment")
def list_seller_fulfillment(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT id, name, sku, stock, price, fulfillment_mode, qc_status
               FROM products WHERE seller_id = ? ORDER BY name""",
            (seller["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@router.put("/seller/products/{product_id}/fulfillment")
def update_seller_fulfillment_mode(
    product_id: str, update: SellerFulfillmentModeUpdate, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        product = _owned_product(connection, seller["id"], product_id)
        connection.execute(
            "UPDATE products SET fulfillment_mode = ? WHERE id = ? AND seller_id = ?",
            (update.fulfillment_mode, product_id, seller["id"]),
        )
        connection.commit()
    return {"product_id": product_id, "fulfillment_mode": update.fulfillment_mode}


@router.get("/seller/logistics/manifests")
def list_seller_manifests(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT m.id, m.hub_name, m.reference, m.status, m.created_at,
                      i.product_id, p.name AS product_name, i.quantity
               FROM seller_dropoff_manifests m
               LEFT JOIN seller_dropoff_manifest_items i ON i.manifest_id = m.id
               LEFT JOIN products p ON p.id = i.product_id
               WHERE m.seller_id = ? ORDER BY m.id DESC""",
            (seller["id"],),
        ).fetchall()
    manifests = {}
    for row in rows:
        manifest = manifests.setdefault(
            row["id"],
            {
                "id": row["id"],
                "hub_name": row["hub_name"],
                "reference": row["reference"],
                "status": row["status"],
                "created_at": row["created_at"],
                "items": [],
            },
        )
        if row["product_id"]:
            manifest["items"].append(
                {
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "quantity": row["quantity"],
                }
            )
    return list(manifests.values())


@router.post("/seller/logistics/manifests", status_code=status.HTTP_201_CREATED)
def create_seller_manifest(
    manifest: SellerDropoffManifestInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    reference = f"VDO-{secrets.token_hex(5).upper()}"
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for item in manifest.items:
            product = _owned_product(connection, seller["id"], item.product_id)
            if product["fulfillment_mode"] != "MAISON_EXPRESS":
                raise HTTPException(
                    status_code=409,
                    detail=f"{product['name']} must use Maison Express before adding it to a manifest.",
                )
            reserved = connection.execute(
                """SELECT COALESCE(SUM(i.quantity), 0)
                   FROM seller_dropoff_manifest_items i
                   JOIN seller_dropoff_manifests m ON m.id = i.manifest_id
                   WHERE m.seller_id = ? AND i.product_id = ? AND m.status = 'READY'""",
                (seller["id"], item.product_id),
            ).fetchone()[0]
            if reserved + item.quantity > product["stock"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Manifest quantity exceeds available stock for {product['name']}.",
                )
        cursor = connection.execute(
            """INSERT INTO seller_dropoff_manifests (seller_id, hub_name, reference)
               VALUES (?, ?, ?)""",
            (seller["id"], manifest.hub_name, reference),
        )
        manifest_id = cursor.lastrowid
        connection.executemany(
            """INSERT INTO seller_dropoff_manifest_items (manifest_id, product_id, quantity)
               VALUES (?, ?, ?)""",
            [
                (manifest_id, item.product_id, item.quantity)
                for item in manifest.items
            ],
        )
        connection.commit()
    return {
        "id": manifest_id,
        "hub_name": manifest.hub_name,
        "reference": reference,
        "status": "READY",
        "items": [item.model_dump() for item in manifest.items],
    }


@router.post("/seller/logistics/manifests/{manifest_id}/dropoff")
def confirm_seller_manifest_dropoff(manifest_id: int, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        manifest = connection.execute(
            """SELECT id, status FROM seller_dropoff_manifests
               WHERE id = ? AND seller_id = ?""",
            (manifest_id, seller["id"]),
        ).fetchone()
        if manifest is None:
            raise HTTPException(status_code=404, detail="The manifest was not found.")
        if manifest["status"] != "READY":
            raise HTTPException(status_code=409, detail="This manifest is no longer ready.")
        items = connection.execute(
            """SELECT product_id, quantity FROM seller_dropoff_manifest_items
               WHERE manifest_id = ?""",
            (manifest_id,),
        ).fetchall()
        for item in items:
            connection.execute(
                """INSERT INTO seller_warehouse_inventory (seller_id, product_id, quantity)
                   VALUES (?, ?, ?)
                   ON CONFLICT(seller_id, product_id) DO UPDATE SET
                       quantity = seller_warehouse_inventory.quantity + excluded.quantity,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (seller["id"], item["product_id"], item["quantity"]),
            )
        connection.execute(
            "UPDATE seller_dropoff_manifests SET status = 'DROPPED_OFF' WHERE id = ?",
            (manifest_id,),
        )
        connection.commit()
    return {"id": manifest_id, "status": "DROPPED_OFF"}


@router.get("/seller/qc")
def list_seller_qc_queue(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        products = connection.execute(
            """SELECT p.id, p.name, p.sku, p.image, p.product_status, p.qc_status,
                      p.fulfillment_mode
               FROM products p WHERE p.seller_id = ? ORDER BY p.name""",
            (seller["id"],),
        ).fetchall()
        latest_audits = connection.execute(
            """SELECT product_id, notes, reviewed_by, created_at
               FROM seller_qc_audits WHERE seller_id = ?
               ORDER BY created_at DESC, id DESC""",
            (seller["id"],),
        ).fetchall()
    audits = {}
    for audit in latest_audits:
        audits.setdefault(audit["product_id"], dict(audit))
    return [
        dict(product)
        | {
            "audit": audits.get(product["id"]),
        }
        for product in products
    ]


@router.post("/seller/products/{product_id}/qc")
def submit_seller_product_qc(product_id: str, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        product = _owned_product(connection, seller["id"], product_id)
        if product["qc_status"] == "PENDING_QC":
            raise HTTPException(
                status_code=409, detail="This product is already waiting for QC review."
            )
        connection.execute(
            """UPDATE products SET qc_status = ?, product_status = ?, active = ?
               WHERE id = ? AND seller_id = ?""",
            ("PENDING_QC", "DRAFT", 0, product_id, seller["id"]),
        )
        connection.execute(
            """INSERT INTO seller_qc_audits
               (seller_id, product_id, qc_status, notes, reviewed_by)
               VALUES (?, ?, 'PENDING_QC', 'Submitted for review.', 'seller')""",
            (seller["id"], product_id),
        )
        connection.commit()
    return {"product_id": product_id, "qc_status": "PENDING_QC"}


@router.post("/seller/vas-requests", status_code=status.HTTP_201_CREATED)
def create_seller_vas_request(
    vas_request: SellerVasRequest, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        _owned_product(connection, seller["id"], vas_request.product_id)
        cursor = connection.execute(
            """INSERT INTO seller_vas_requests (seller_id, product_id, service_type)
               VALUES (?, ?, ?)""",
            (seller["id"], vas_request.product_id, vas_request.service_type),
        )
        connection.commit()
    return {
        "id": cursor.lastrowid,
        "product_id": vas_request.product_id,
        "service_type": vas_request.service_type,
        "status": "REQUESTED",
        "fulfillment_status": "MANUAL_QUEUE",
    }


@router.get("/seller/statements/weekly")
def get_seller_weekly_statement(request: Request) -> dict:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT so.id AS sub_order_id, o.order_number, o.created_at,
                      so.subtotal AS gross_revenue,
                      so.commission_amount AS commission,
                      so.seller_payout_amount AS net_balance,
                      so.fulfillment_status, o.payment_status
               FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
               WHERE so.seller_id = ? AND o.created_at >= datetime('now', '-7 days')
               ORDER BY o.created_at DESC""",
            (seller["id"],),
        ).fetchall()
        statement_rows = []
        for row in rows:
            commission_vat = round(row["commission"] * 0.16, 2)
            connection.execute(
                """INSERT INTO seller_financial_statement_rows
                   (seller_id, sub_order_id, gross_revenue, commission,
                    commission_vat, shipping_contribution, net_balance)
                   VALUES (?, ?, ?, ?, ?, 0, ?)
                   ON CONFLICT(sub_order_id) DO UPDATE SET
                     gross_revenue = excluded.gross_revenue,
                     commission = excluded.commission,
                     commission_vat = excluded.commission_vat,
                     net_balance = excluded.net_balance""",
                (
                    seller["id"],
                    row["sub_order_id"],
                    row["gross_revenue"],
                    row["commission"],
                    commission_vat,
                    row["net_balance"],
                ),
            )
            statement_rows.append(
                dict(row)
                | {
                    "commission_vat": commission_vat,
                    "shipping_contribution": 0,
                }
            )
        penalties = connection.execute(
            """SELECT id, sub_order_id, product_id, reason, amount, status, created_at
               FROM seller_penalty_events WHERE seller_id = ?
                 AND created_at >= datetime('now', '-7 days')
               ORDER BY created_at DESC""",
            (seller["id"],),
        ).fetchall()
        connection.commit()
    totals = {
        key: round(sum(row[key] for row in statement_rows), 2)
        for key in (
            "gross_revenue",
            "commission",
            "commission_vat",
            "shipping_contribution",
            "net_balance",
        )
    }
    return {
        "period": "last_7_days",
        "rows": statement_rows,
        "penalties": [dict(row) for row in penalties],
        "totals": totals,
        "notes": [
            "Commission VAT is shown as an estimate and is not included in the existing payout calculation.",
            "Shipping contribution is zero until a shipping fee is recorded.",
        ],
    }


@router.get("/seller/repricing")
def list_seller_repricing_rules(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT r.*, p.name AS product_name, p.price AS current_price
               FROM seller_repricing_rules r JOIN products p ON p.id = r.product_id
               WHERE r.seller_id = ? ORDER BY r.updated_at DESC""",
            (seller["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@router.put("/seller/products/{product_id}/repricing")
def update_seller_repricing_rule(
    product_id: str, rule: SellerRepricingRuleInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        product = _owned_product(connection, seller["id"], product_id)
        if rule.rule == "CLEARANCE_DISCOUNT":
            target_price = product["price"] * 0.9
        else:
            market_price = connection.execute(
                """SELECT MIN(price) FROM products
                   WHERE category = ? AND seller_id != ? AND active = 1
                     AND product_status = 'ACTIVE'""",
                (product["category"], seller["id"]),
            ).fetchone()[0]
            target_price = market_price if market_price is not None else product["price"]
        applied_price = round(
            min(rule.max_price, max(rule.min_price, target_price)), 2
        )
        connection.execute(
            """INSERT INTO seller_repricing_rules
               (seller_id, product_id, min_price, max_price, rule, applied_price)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(product_id) DO UPDATE SET
                 seller_id = excluded.seller_id,
                 min_price = excluded.min_price,
                 max_price = excluded.max_price,
                 rule = excluded.rule,
                 applied_price = excluded.applied_price,
                 updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (
                seller["id"],
                product_id,
                rule.min_price,
                rule.max_price,
                rule.rule,
                applied_price,
            ),
        )
        connection.execute(
            "UPDATE products SET old_price = price, price = ? WHERE id = ?",
            (applied_price, product_id),
        )
        connection.commit()
    return {
        "product_id": product_id,
        "rule": rule.rule,
        "applied_price": applied_price,
        "market_data": "Marketplace catalog comparison; no external competitor feed is connected.",
    }


@router.get("/seller/branches")
def list_seller_branches(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        branches = connection.execute(
            """SELECT id, name, address, city, phone, active, created_at
               FROM seller_branches WHERE seller_id = ? ORDER BY name""",
            (seller["id"],),
        ).fetchall()
        inventory = connection.execute(
            """SELECT i.branch_id, i.product_id, p.name AS product_name,
                      i.quantity, i.updated_at
               FROM seller_branch_inventory i
               JOIN seller_branches b ON b.id = i.branch_id
               JOIN products p ON p.id = i.product_id
               WHERE b.seller_id = ? ORDER BY p.name""",
            (seller["id"],),
        ).fetchall()
    inventory_by_branch = {}
    for item in inventory:
        inventory_by_branch.setdefault(item["branch_id"], []).append(
            {key: item[key] for key in ("product_id", "product_name", "quantity")}
        )
    return [
        dict(branch) | {"inventory": inventory_by_branch.get(branch["id"], [])}
        for branch in branches
    ]


@router.post("/seller/branches", status_code=status.HTTP_201_CREATED)
def create_seller_branch(branch: SellerBranchCreate, request: Request) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """INSERT INTO seller_branches
                   (seller_id, name, address, city, phone) VALUES (?, ?, ?, ?, ?)""",
                (seller["id"], branch.name, branch.address, branch.city, branch.phone),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409, detail="A branch with this name already exists."
            ) from error
        connection.commit()
    return {"id": cursor.lastrowid, **branch.model_dump(), "active": True}


@router.put("/seller/branches/{branch_id}/inventory")
def update_seller_branch_inventory(
    branch_id: int, update: SellerBranchInventoryUpdate, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        branch = connection.execute(
            "SELECT id FROM seller_branches WHERE id = ? AND seller_id = ? AND active = 1",
            (branch_id, seller["id"]),
        ).fetchone()
        if branch is None:
            raise HTTPException(status_code=404, detail="The branch was not found.")
        for item in update.items:
            product = _owned_product(connection, seller["id"], item.product_id)
            allocated_elsewhere = connection.execute(
                """SELECT COALESCE(SUM(i.quantity), 0)
                   FROM seller_branch_inventory i
                   JOIN seller_branches b ON b.id = i.branch_id
                   WHERE i.product_id = ? AND b.seller_id = ? AND b.id != ?""",
                (item.product_id, seller["id"], branch_id),
            ).fetchone()[0]
            if allocated_elsewhere + item.quantity > product["stock"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Branch allocations cannot exceed available stock for {product['name']}.",
                )
        connection.executemany(
            """INSERT INTO seller_branch_inventory (branch_id, product_id, quantity)
               VALUES (?, ?, ?)
               ON CONFLICT(branch_id, product_id) DO UPDATE SET
                 quantity = excluded.quantity,
                 updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            [
                (branch_id, item.product_id, item.quantity) for item in update.items
            ],
        )
        connection.commit()
    return {"branch_id": branch_id, "updated": len(update.items)}


@router.get("/seller/restock")
def get_seller_restock_plan(request: Request) -> list[dict]:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        products = connection.execute(
            """SELECT p.id, p.name, p.stock, p.low_stock_threshold,
                      COALESCE(SUM(CASE WHEN o.id IS NOT NULL
                           AND o.created_at >= datetime('now', '-30 days')
                           AND o.payment_status IN ('paid', 'completed_demo')
                           THEN oi.quantity ELSE 0 END), 0) AS units_sold_30d
               FROM products p
               LEFT JOIN order_items oi ON oi.product_id = p.id
               LEFT JOIN orders o ON o.id = oi.order_id
               WHERE p.seller_id = ?
               GROUP BY p.id ORDER BY p.stock ASC, p.name""",
            (seller["id"],),
        ).fetchall()
        requests = connection.execute(
            """SELECT product_id, MAX(created_at) AS latest_request
               FROM seller_restock_recommendations WHERE seller_id = ?
                 AND status = 'REQUESTED' GROUP BY product_id""",
            (seller["id"],),
        ).fetchall()
    latest = {row["product_id"]: row["latest_request"] for row in requests}
    result = []
    for product in products:
        velocity = product["units_sold_30d"] / 30
        result.append(
            dict(product)
            | {
                "daily_velocity": round(velocity, 2),
                "days_of_supply": (
                    round(product["stock"] / velocity, 1) if velocity else None
                ),
                "recommended_quantity": max(
                    0, round(velocity * 30 - product["stock"])
                ),
                "low_stock": product["stock"] < product["low_stock_threshold"],
                "latest_request": latest.get(product["id"]),
            }
        )
    return result


@router.post("/seller/products/{product_id}/restock", status_code=status.HTTP_201_CREATED)
def request_seller_restock(
    product_id: str,
    recommendation: SellerRestockRecommendationInput,
    request: Request,
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        _owned_product(connection, seller["id"], product_id)
        cursor = connection.execute(
            """INSERT INTO seller_restock_recommendations
               (seller_id, product_id, recommended_quantity) VALUES (?, ?, ?)""",
            (seller["id"], product_id, recommendation.recommended_quantity),
        )
        connection.commit()
    return {
        "id": cursor.lastrowid,
        "product_id": product_id,
        "recommended_quantity": recommendation.recommended_quantity,
        "status": "REQUESTED",
        "message": "Restock recommendation recorded; no purchase order was sent.",
    }


@router.post(
    "/seller/orders/{sub_order_id}/review-request",
    status_code=status.HTTP_201_CREATED,
)
def request_seller_order_review(
    sub_order_id: int, review: SellerReviewRequestInput, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        order = connection.execute(
            """SELECT so.id, so.fulfillment_status, o.payment_status, o.customer_phone
               FROM sub_orders so JOIN orders o ON o.id = so.parent_order_id
               WHERE so.id = ? AND so.seller_id = ?""",
            (sub_order_id, seller["id"]),
        ).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Your order was not found.")
        if (
            order["fulfillment_status"] != "DELIVERED"
            or order["payment_status"] not in ("paid", "completed_demo")
        ):
            raise HTTPException(
                status_code=409,
                detail="Review requests are available after a paid order is delivered.",
            )
        destination = order["customer_phone"]
        if review.channel == "EMAIL":
            destination = ""
        hint = f"••••{destination[-4:]}" if destination else ""
        try:
            cursor = connection.execute(
                """INSERT INTO seller_review_requests
                   (seller_id, sub_order_id, channel, destination_hint, status)
                   VALUES (?, ?, ?, ?, 'SIMULATED')""",
                (seller["id"], sub_order_id, review.channel, hint),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409,
                detail=f"A {review.channel.lower()} review request was already recorded for this order.",
            ) from error
        connection.commit()
    return {
        "id": cursor.lastrowid,
        "sub_order_id": sub_order_id,
        "channel": review.channel,
        "destination_hint": hint,
        "status": "SIMULATED",
        "message": "Audit record saved; no email or SMS provider is configured.",
    }


@router.get("/seller/insights")
def get_seller_insights(request: Request) -> dict:
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        products = connection.execute(
            """SELECT p.id, p.name, p.category, p.price, p.stock,
                      COALESCE(SUM(CASE WHEN o.created_at >= datetime('now', '-30 days')
                           AND o.payment_status IN ('paid', 'completed_demo')
                           THEN oi.quantity ELSE 0 END), 0) AS units_sold_30d
               FROM products p
               LEFT JOIN order_items oi ON oi.product_id = p.id
               LEFT JOIN orders o ON o.id = oi.order_id
               WHERE p.seller_id = ? GROUP BY p.id ORDER BY units_sold_30d DESC""",
            (seller["id"],),
        ).fetchall()
    recommendations = []
    for product in products:
        velocity = product["units_sold_30d"] / 30
        if product["stock"] < 5:
            recommendations.append(
                {
                    "type": "RESTOCK",
                    "product_id": product["id"],
                    "title": f"Restock {product['name']}",
                    "detail": f"Only {product['stock']} units remain.",
                }
            )
        elif velocity and product["stock"] / velocity < 14:
            recommendations.append(
                {
                    "type": "VELOCITY",
                    "product_id": product["id"],
                    "title": f"Plan replenishment for {product['name']}",
                    "detail": f"About {round(product['stock'] / velocity)} days of supply remain.",
                }
            )
    top_categories = {}
    for product in products:
        top_categories[product["category"]] = (
            top_categories.get(product["category"], 0) + product["units_sold_30d"]
        )
    return {
        "source": "Rule-based demo insights from this seller's 30-day order history.",
        "recommendations": recommendations[:10],
        "top_categories": sorted(
            [
                {"category": category, "units_sold_30d": quantity}
                for category, quantity in top_categories.items()
            ],
            key=lambda row: row["units_sold_30d"],
            reverse=True,
        )[:5],
    }
