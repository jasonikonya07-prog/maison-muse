import json
import os
import secrets
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Request, status

from app.auth_security import decode_access_token
from app.config import get_database_url
from app.data_encryption import phone_lookup_hash
from app.database import get_connection
from app.order_tracking import (
    apply_seller_fulfillment,
    decoded_items,
    effective_fulfillment_status,
    publish_order_update,
    record_order_status_event,
    status_timeline,
)
from app.pesapal import PesapalError, get_config, submit_order
from app.routers.products import expire_seller_promotions
from app.routers.sellers import _verify_seller_write, require_seller
from app.schemas import DemoCheckoutInput, OrderCreate, SellerFulfillmentUpdate


router = APIRouter()
FREE_SHIPPING_THRESHOLD_CENTS = 5000 * 100
SHIPPING_FEE_CENTS = 250 * 100
DEFAULT_COMMISSION_PERCENTAGE = Decimal("10")


def to_currency(cents: int) -> float:
    return round(cents / 100, 2)


def _buyer_id_from_request(request: Request, connection) -> int | None:
    authorization = request.headers.get("authorization", "")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Your sign-in is invalid.")
    claims = decode_access_token(token)
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Your sign-in is invalid.") from None
    user = connection.execute(
        "SELECT id, role FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None or user["role"] != claims.get("role"):
        raise HTTPException(status_code=401, detail="Your buyer account is unavailable.")
    if user["role"] == "seller":
        return None
    if user["role"] != "buyer":
        raise HTTPException(status_code=403, detail="A buyer account is required.")
    return user_id


@router.post("/orders/checkout", status_code=status.HTTP_201_CREATED)
def demo_checkout(order: DemoCheckoutInput, request: Request) -> dict:
    if os.getenv("DEMO_CHECKOUT_ENABLED", "").strip().casefold() != "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo checkout is disabled. Enable DEMO_CHECKOUT_ENABLED only in a demo environment.",
        )

    requested_by_product: dict[str, int] = defaultdict(int)
    for item in order.items:
        requested_by_product[item.product_id] += item.quantity

    with get_connection() as connection:
        expire_seller_promotions(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            buyer_id = _buyer_id_from_request(request, connection)
            products = {}
            for product_id, requested_quantity in requested_by_product.items():
                product = connection.execute(
                    """
                    SELECT p.id, p.name, p.price, p.stock, p.seller_id,
                           p.is_agri_product,
                           p.category, s.status AS seller_status,
                           s.maintenance_mode AS seller_maintenance_mode,
                           s.review_state AS seller_review_state,
                           s.holiday_mode AS seller_holiday_mode,
                           s.store_name, s.store_slug,
                           s.selected_plan, s.commission_rate,
                           s.commission_percentage, s.commission_is_custom
                    FROM products p
                    LEFT JOIN sellers s ON s.id = p.seller_id
                    WHERE p.id = ? AND p.active = 1
                      AND p.product_status = 'ACTIVE'
                    """,
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise HTTPException(
                        status_code=404, detail=f"Product '{product_id}' was not found."
                    )
                if product["is_agri_product"]:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"{product['name']} is sold directly by the farmer. "
                            "Contact the seller on WhatsApp instead of using marketplace checkout."
                        ),
                    )
                if product["seller_id"] is not None and (
                    product["seller_status"] != "APPROVED"
                    or product["seller_review_state"] != "CLEAR"
                    or product["seller_maintenance_mode"]
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"{product['name']} is currently unavailable.",
                    )
                if product["seller_id"] is not None and product["seller_holiday_mode"]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"{product['store_name']} is temporarily pausing new orders.",
                    )
                if requested_quantity > product["stock"]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Not enough stock available for {product['name']}.",
                    )
                products[product_id] = product

            setting = connection.execute(
                "SELECT value FROM store_settings WHERE key = 'marketplace_default_commission'"
            ).fetchone()
            default_commission = (
                Decimal(setting["value"]) if setting else DEFAULT_COMMISSION_PERCENTAGE
            )
            category_rates = {
                (row["seller_id"], row["category"]): Decimal(str(row["percentage"]))
                for row in connection.execute(
                    "SELECT seller_id, category, percentage FROM marketplace_commission_category_rates"
                )
            }

            item_rows = []
            seller_items: dict[int, list[dict]] = defaultdict(list)
            seller_subtotals: dict[int, int] = defaultdict(int)
            seller_commissions: dict[int, int] = defaultdict(int)
            subtotal_cents = 0
            for item in order.items:
                product = products[item.product_id]
                unit_price_cents = int(
                    (Decimal(str(product["price"])) * 100).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                line_cents = unit_price_cents * item.quantity
                subtotal_cents += line_cents
                if product["seller_id"] is not None:
                    seller_id = product["seller_id"]
                    commission_rate = (
                        Decimal(str(product["commission_rate"]))
                        if product["selected_plan"]
                        else Decimal(str(product["commission_percentage"]))
                        if product["commission_is_custom"]
                        else category_rates.get(
                            (seller_id, product["category"]),
                            category_rates.get((0, product["category"]), default_commission),
                        )
                    )
                    seller_commissions[seller_id] += int(
                        (Decimal(line_cents) * commission_rate / 100).quantize(
                            Decimal("1"), rounding=ROUND_HALF_UP
                        )
                    )
                    seller_subtotals[seller_id] += line_cents
                    seller_items[seller_id].append(
                        {
                            "product_id": product["id"],
                            "product_name": product["name"],
                            "unit_price": to_currency(unit_price_cents),
                            "quantity": item.quantity,
                            "variant": item.variant,
                        }
                    )
                item_rows.append(
                    (
                        product["id"],
                        product["name"],
                        unit_price_cents,
                        item.quantity,
                        item.variant,
                    )
                )
                connection.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (item.quantity, product["id"]),
                )

            shipping_cents = (
                0 if subtotal_cents >= FREE_SHIPPING_THRESHOLD_CENTS else SHIPPING_FEE_CENTS
            )
            tax_cents = (subtotal_cents * 8 + 50) // 100
            order_number = f"MM-DEMO-{secrets.token_hex(8).upper()}"
            transaction_reference = f"MPESA-{secrets.token_hex(4).upper()}"
            delivery_address = f"{order.customer.address}, {order.city}"
            if order.delivery_notes:
                delivery_address = f"{delivery_address} · {order.delivery_notes}"
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    order_number, tracking_id, buyer_id, customer_name, customer_phone,
                    customer_phone_lookup_hash, delivery_address,
                    payment_method, payment_gateway, gateway_status, status,
                    payment_status, mpesa_phone, gateway_reference, subtotal_cents,
                    shipping_cents, tax_cents, total_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'mobile-money', 'Demo M-Pesa',
                          'ESCROW PAID (DEMO)', 'completed', 'completed_demo',
                          ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_number,
                    order_number,
                    buyer_id,
                    order.customer.name,
                    order.customer.phone,
                    (
                        phone_lookup_hash(order.customer.phone)
                        if get_database_url()
                        else ""
                    ),
                    delivery_address,
                    order.mpesa_phone,
                    transaction_reference,
                    subtotal_cents,
                    shipping_cents,
                    tax_cents,
                    subtotal_cents + shipping_cents + tax_cents,
                ),
            )
            order_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO order_items (
                    order_id, product_id, product_name, unit_price_cents,
                    quantity, variant
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(order_id, *item_row) for item_row in item_rows],
            )
            seller_receipts = []
            for seller_id, seller_order_items in seller_items.items():
                gross_cents = seller_subtotals[seller_id]
                commission_cents = seller_commissions[seller_id]
                seller_product = next(
                    product for product in products.values()
                    if product["seller_id"] == seller_id
                )
                sub_order = connection.execute(
                    """
                    INSERT INTO sub_orders (
                        parent_order_id, seller_id, items_json, subtotal,
                        commission_amount, seller_payout_amount
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        seller_id,
                        json.dumps(seller_order_items),
                        to_currency(gross_cents),
                        to_currency(commission_cents),
                        to_currency(gross_cents - commission_cents),
                    ),
                )
                record_order_status_event(
                    connection,
                    order_id,
                    sub_order.lastrowid,
                    "ORDER_PLACED",
                    "system",
                    "Order placed; demo escrow is confirmed.",
                )
                gross_amount = to_currency(gross_cents)
                commission_amount = to_currency(commission_cents)
                net_amount = to_currency(gross_cents - commission_cents)
                connection.execute(
                    """
                    INSERT INTO seller_payout_ledger (
                        seller_id, sub_order_id, gross_amount, commission_amount,
                        net_amount, status, transaction_reference
                    ) VALUES (?, ?, ?, ?, ?, 'ESCROW PAID (DEMO)', ?)
                    """,
                    (
                        seller_id,
                        sub_order.lastrowid,
                        gross_amount,
                        commission_amount,
                        net_amount,
                        transaction_reference,
                    ),
                )
                seller_receipts.append(
                    {
                        "seller_id": seller_id,
                        "store_name": seller_product["store_name"],
                        "store_slug": seller_product["store_slug"],
                        "sub_order_id": sub_order.lastrowid,
                        "gross_amount": gross_amount,
                        "commission_amount": commission_amount,
                        "net_amount": net_amount,
                        "status": "ESCROW PAID (DEMO)",
                        "items": seller_order_items,
                    }
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "order_number": order_number,
        "tracking_id": order_number,
        "master_tracking_id": order_number,
        "transaction_reference": transaction_reference,
        "status": "COMPLETED (DEMO)",
        "payment_status": "COMPLETED (DEMO)",
        "payment_method": "mobile-money",
        "currency": "KES",
        "subtotal": to_currency(subtotal_cents),
        "shipping": to_currency(shipping_cents),
        "tax": to_currency(tax_cents),
        "total": to_currency(subtotal_cents + shipping_cents + tax_cents),
        "is_demo": True,
        "sub_orders": seller_receipts,
    }


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate, request: Request) -> dict:
    try:
        get_config()
    except PesapalError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Online payment is not available: {error}",
        ) from error

    requested_by_product: dict[str, int] = defaultdict(int)
    for item in order.items:
        requested_by_product[item.product_id] += item.quantity

    with get_connection() as connection:
        expire_seller_promotions(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            buyer_id = _buyer_id_from_request(request, connection)
            products = {}
            for product_id, requested_quantity in requested_by_product.items():
                product = connection.execute(
                    """
                    SELECT p.id, p.name, p.price, p.stock, p.seller_id,
                           p.is_agri_product,
                           p.category, s.commission_percentage,
                           s.commission_is_custom, s.selected_plan,
                           s.commission_rate, s.status AS seller_status,
                           s.maintenance_mode AS seller_maintenance_mode,
                           s.review_state AS seller_review_state,
                           s.holiday_mode AS seller_holiday_mode
                    FROM products p
                    LEFT JOIN sellers s ON s.id = p.seller_id
                    WHERE p.id = ? AND p.active = 1
                      AND p.product_status = 'ACTIVE'
                    """,
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Product '{product_id}' was not found.",
                    )
                if product["is_agri_product"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"{product['name']} is sold directly by the farmer. "
                            "Contact the seller on WhatsApp instead of using marketplace checkout."
                        ),
                    )
                if product["seller_id"] is not None and (
                    product["seller_status"] != "APPROVED"
                    or product["seller_review_state"] != "CLEAR"
                    or product["seller_maintenance_mode"]
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"{product['name']} is currently unavailable.",
                    )
                if product["seller_id"] is not None and product["seller_holiday_mode"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This seller is temporarily pausing new orders.",
                    )
                if requested_quantity > product["stock"]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Not enough stock available for {product['name']}.",
                    )
                products[product_id] = product

            setting = connection.execute(
                "SELECT value FROM store_settings WHERE key = 'marketplace_default_commission'"
            ).fetchone()
            default_commission = (
                Decimal(setting["value"]) if setting else DEFAULT_COMMISSION_PERCENTAGE
            )
            category_rates = {
                (row["seller_id"], row["category"]): Decimal(str(row["percentage"]))
                for row in connection.execute(
                    "SELECT seller_id, category, percentage FROM marketplace_commission_category_rates"
                )
            }

            item_rows = []
            seller_items: dict[int, list[dict]] = defaultdict(list)
            seller_subtotals: dict[int, int] = defaultdict(int)
            seller_commission_cents: dict[int, int] = defaultdict(int)
            subtotal_cents = 0
            for item in order.items:
                product = products[item.product_id]
                unit_price_cents = int(
                    (Decimal(str(product["price"])) * 100).quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    )
                )
                subtotal_cents += unit_price_cents * item.quantity
                if product["seller_id"] is not None:
                    seller_id = product["seller_id"]
                    if product["selected_plan"]:
                        commission_rate = Decimal(str(product["commission_rate"]))
                    else:
                        base_rate = (
                            Decimal(str(product["commission_percentage"]))
                            if product["commission_is_custom"]
                            else default_commission
                        )
                        commission_rate = category_rates.get(
                            (seller_id, product["category"]),
                            category_rates.get((0, product["category"]), base_rate),
                        )
                    line_subtotal_cents = unit_price_cents * item.quantity
                    seller_commission_cents[seller_id] += int(
                        (
                            Decimal(line_subtotal_cents) * commission_rate / 100
                        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    )
                    seller_items[product["seller_id"]].append(
                        {
                            "product_id": item.product_id,
                            "product_name": product["name"],
                            "unit_price": to_currency(unit_price_cents),
                            "quantity": item.quantity,
                            "variant": item.variant,
                        }
                    )
                    seller_subtotals[seller_id] += line_subtotal_cents
                item_rows.append(
                    (
                        item.product_id,
                        product["name"],
                        unit_price_cents,
                        item.quantity,
                        item.variant,
                    )
                )

            shipping_cents = (
                0
                if subtotal_cents >= FREE_SHIPPING_THRESHOLD_CENTS
                else SHIPPING_FEE_CENTS
            )
            tax_cents = (subtotal_cents * 8 + 50) // 100
            total_cents = subtotal_cents + shipping_cents + tax_cents
            order_number = f"MM-{secrets.token_hex(16).upper()}"
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    order_number, tracking_id, buyer_id, customer_name, customer_phone,
                    customer_phone_lookup_hash, delivery_address,
                    payment_method, payment_gateway, status, payment_status,
                    payment_attempts, subtotal_cents, shipping_cents, tax_cents,
                    total_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pesapal', 'Pesapal', 'pending',
                          'pending_callback', 1, ?, ?, ?, ?)
                """,
                (
                    order_number,
                    order_number,
                    buyer_id,
                    order.customer.name,
                    order.customer.phone,
                    (
                        phone_lookup_hash(order.customer.phone)
                        if get_database_url()
                        else ""
                    ),
                    order.customer.address,
                    subtotal_cents,
                    shipping_cents,
                    tax_cents,
                    total_cents,
                ),
            )
            connection.executemany(
                """
                INSERT INTO order_items (
                    order_id, product_id, product_name, unit_price_cents, quantity, variant
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(cursor.lastrowid, *item_row) for item_row in item_rows],
            )
            for seller_id, items in seller_items.items():
                seller_subtotal_cents = seller_subtotals[seller_id]
                commission_cents = seller_commission_cents[seller_id]
                sub_order = connection.execute(
                    """
                    INSERT INTO sub_orders (
                        parent_order_id, seller_id, items_json, subtotal,
                        commission_amount, seller_payout_amount
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cursor.lastrowid,
                        seller_id,
                        json.dumps(items),
                        to_currency(seller_subtotal_cents),
                        to_currency(commission_cents),
                        to_currency(seller_subtotal_cents - commission_cents),
                    ),
                )
                record_order_status_event(
                    connection,
                    cursor.lastrowid,
                    sub_order.lastrowid,
                    "ORDER_PLACED",
                    "system",
                    "Order placed; payment confirmation is pending.",
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    try:
        payment = submit_order(
            order_number=order_number,
            amount_cents=total_cents,
            customer_name=order.customer.name,
            phone_number=order.customer.phone,
            delivery_address=order.customer.address,
        )
    except PesapalError as error:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE orders
                SET payment_status = 'failed', gateway_status = ?
                WHERE order_number = ?
                """,
                (str(error), order_number),
            )
            connection.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not start Pesapal checkout: {error}",
        ) from error

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE orders
            SET gateway_reference = ?, gateway_tracking_id = ?
            WHERE order_number = ?
            """,
            (
                payment["merchant_reference"],
                payment["tracking_id"],
                order_number,
            ),
        )
        connection.commit()

    return {
        "order_number": order_number,
        "tracking_id": order_number,
        "status": "pending",
        "payment_status": "pending_callback",
        "payment_method": "pesapal",
        "payment_gateway": "Pesapal",
        "currency": "KES",
        "subtotal": to_currency(subtotal_cents),
        "shipping": to_currency(shipping_cents),
        "tax": to_currency(tax_cents),
        "total": to_currency(total_cents),
        "redirect_url": payment["redirect_url"],
    }


@router.put("/orders/{order_id}/status")
def update_seller_sub_order_status(
    order_id: int, update: SellerFulfillmentUpdate, request: Request
) -> dict:
    _verify_seller_write(request)
    seller = require_seller(request, approved=True)
    with get_connection() as connection:
        target_status, parent_order_id = apply_seller_fulfillment(
            connection,
            order_id,
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
    publish_order_update(request, parent_order_id, order_id, display_status)
    return {
        "id": order_id,
        "fulfillment_status": target_status,
        "pipeline_status": update.status,
        "courier_name": update.courier_name,
        "tracking_number": update.tracking_number,
    }


@router.get("/orders/track/{tracking_id}")
def track_marketplace_order(tracking_id: str) -> dict:
    normalized_id = tracking_id.strip()
    if not normalized_id or len(normalized_id) > 160:
        raise HTTPException(status_code=404, detail="Order tracking details were not found.")
    with get_connection() as connection:
        order = connection.execute(
            """
            SELECT o.*,
                   CASE WHEN so.tracking_number = ? THEN so.id END
                       AS matched_sub_order_id
            FROM orders o
            LEFT JOIN sub_orders so ON so.parent_order_id = o.id
            WHERE o.tracking_id = ? OR o.order_number = ?
               OR so.tracking_number = ?
            ORDER BY CASE WHEN so.tracking_number = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (
                normalized_id,
                normalized_id,
                normalized_id,
                normalized_id,
                normalized_id,
            ),
        ).fetchone()
        if order is None:
            raise HTTPException(
                status_code=404, detail="Order tracking details were not found."
            )
        sub_order_clause = "AND so.id = ?" if order["matched_sub_order_id"] else ""
        parameters: tuple[object, ...] = (
            (order["id"], order["matched_sub_order_id"])
            if order["matched_sub_order_id"]
            else (order["id"],)
        )
        sub_orders = connection.execute(
            f"""
            SELECT so.*, s.store_name
            FROM sub_orders so JOIN sellers s ON s.id = so.seller_id
            WHERE so.parent_order_id = ? {sub_order_clause}
            ORDER BY so.id
            """,
            parameters,
        ).fetchall()
        packages = []
        for sub_order in sub_orders:
            timeline = status_timeline(connection, sub_order["id"])
            if not timeline:
                timeline = [
                    {
                        "status": "ORDER_PLACED",
                        "actor": "system",
                        "note": "Order placed.",
                        "created_at": order["created_at"],
                    }
                ]
            packages.append(
                {
                    "id": sub_order["id"],
                    "seller_name": sub_order["store_name"],
                    "items": decoded_items(sub_order["items_json"]),
                    "subtotal": sub_order["subtotal"],
                    "commission_amount": sub_order["commission_amount"],
                    "seller_payout_amount": sub_order["seller_payout_amount"],
                    "status": effective_fulfillment_status(sub_order),
                    "courier_name": sub_order["courier_name"],
                    "tracking_number": sub_order["tracking_number"],
                    "updated_at": sub_order["updated_at"],
                    "timeline": timeline,
                }
            )
        if not packages:
            items = connection.execute(
                """
                SELECT product_id, product_name, unit_price_cents, quantity, variant
                FROM order_items WHERE order_id = ? ORDER BY id
                """,
                (order["id"],),
            ).fetchall()
            packages.append(
                {
                    "id": None,
                    "seller_name": "",
                    "items": [
                        {
                            "product_id": item["product_id"],
                            "product_name": item["product_name"],
                            "unit_price": item["unit_price_cents"] / 100,
                            "quantity": item["quantity"],
                            "variant": item["variant"],
                        }
                        for item in items
                    ],
                    "subtotal": order["subtotal_cents"] / 100,
                    "commission_amount": 0,
                    "seller_payout_amount": 0,
                    "status": order["status"],
                    "courier_name": "",
                    "tracking_number": "",
                    "updated_at": order["created_at"],
                    "timeline": [],
                }
            )
    return {
        "order_number": order["order_number"],
        "tracking_id": order["tracking_id"] or order["order_number"],
        "status": packages[0]["status"] if len(packages) == 1 else "MULTI_VENDOR",
        "payment_status": order["payment_status"],
        "buyer": {
            "name": order["customer_name"],
            "phone": order["customer_phone"],
            "delivery_address": order["delivery_address"],
        },
        "created_at": order["created_at"],
        "subtotal": order["subtotal_cents"] / 100,
        "shipping": order["shipping_cents"] / 100,
        "tax": order["tax_cents"] / 100,
        "total": order["total_cents"] / 100,
        "packages": packages,
    }


@router.get("/orders/mine")
def list_buyer_orders(request: Request) -> list[dict]:
    with get_connection() as connection:
        buyer_id = _buyer_id_from_request(request, connection)
        if buyer_id is None:
            raise HTTPException(status_code=401, detail="Sign in to view your orders.")
        orders = connection.execute(
            """
            SELECT id, order_number, tracking_id, status, payment_status,
                   total_cents, created_at
            FROM orders
            WHERE buyer_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (buyer_id,),
        ).fetchall()
        result = []
        for order in orders:
            sub_orders = connection.execute(
                """
                SELECT so.*, s.store_name
                FROM sub_orders so
                JOIN sellers s ON s.id = so.seller_id
                WHERE so.parent_order_id = ?
                ORDER BY so.id
                """,
                (order["id"],),
            ).fetchall()
            packages = [
                {
                    "seller_name": sub_order["store_name"],
                    "status": effective_fulfillment_status(sub_order),
                }
                for sub_order in sub_orders
            ]
            result.append(
                {
                    "order_number": order["order_number"],
                    "tracking_id": order["tracking_id"] or order["order_number"],
                    "status": (
                        packages[0]["status"]
                        if len(packages) == 1
                        else "MULTI_VENDOR"
                        if packages
                        else order["status"].upper()
                    ),
                    "payment_status": order["payment_status"],
                    "total": order["total_cents"] / 100,
                    "created_at": order["created_at"],
                    "packages": packages,
                }
            )
        return result
