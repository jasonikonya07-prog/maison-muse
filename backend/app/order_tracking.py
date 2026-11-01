import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from app.database import get_connection


FULFILLMENT_STATUS_LABELS = {
    "PENDING": "PENDING_PACKING",
    "PROCESSING": "PACKED",
    "SHIPPED": "DISPATCHED_TO_COURIER",
    "DELIVERED": "DELIVERED",
}


def effective_fulfillment_status(row: sqlite3.Row) -> str:
    return row["admin_override_status"] or FULFILLMENT_STATUS_LABELS.get(
        row["fulfillment_status"], row["fulfillment_status"]
    )


def record_order_status_event(
    connection: sqlite3.Connection,
    parent_order_id: int,
    sub_order_id: int,
    status: str,
    actor: str,
    note: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO order_status_events (
            parent_order_id, sub_order_id, status, actor, note
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (parent_order_id, sub_order_id, status, actor, note),
    )


def status_timeline(
    connection: sqlite3.Connection, sub_order_id: int
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT status, actor, note, created_at
        FROM order_status_events
        WHERE sub_order_id = ?
        ORDER BY created_at, id
        """,
        (sub_order_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def decoded_items(value: str) -> list[dict[str, Any]]:
    items = json.loads(value)
    if not isinstance(items, list):
        raise ValueError("Stored order items are not a list.")
    return items


def apply_seller_fulfillment(
    connection: sqlite3.Connection,
    sub_order_id: int,
    seller_id: int,
    requested_status: str,
    courier_name: str,
    tracking_number: str,
) -> tuple[str, int]:
    row = connection.execute(
        """
        SELECT id, parent_order_id, fulfillment_status, admin_override_status
        FROM sub_orders
        WHERE id = ? AND seller_id = ?
        """,
        (sub_order_id, seller_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Your order was not found.")

    canonical = {
        "PENDING_PACKING": "PENDING",
        "PROCESSING": "PROCESSING",
        "PACKED_AND_READY": "PROCESSING",
        "SHIPPED": "SHIPPED",
        "DISPATCHED_TO_COURIER": "SHIPPED",
        "DELIVERED": "DELIVERED",
        "DELIVERED_TO_CUSTOMER": "DELIVERED",
    }
    target_status = canonical[requested_status]
    current_display = row["admin_override_status"] or FULFILLMENT_STATUS_LABELS.get(
        row["fulfillment_status"], row["fulfillment_status"]
    )
    if current_display == "CANCELLED":
        raise HTTPException(status_code=409, detail="A cancelled order cannot be advanced.")
    sequence = {"PENDING": 0, "PROCESSING": 1, "SHIPPED": 2, "DELIVERED": 3}
    current_status = {
        "PENDING_PACKING": "PENDING",
        "PACKED": "PROCESSING",
        "PACKED_AND_READY": "PROCESSING",
        "DISPATCHED_TO_COURIER": "SHIPPED",
        "OUT_FOR_DELIVERY": "SHIPPED",
        "DELIVERED": "DELIVERED",
    }.get(current_display, row["fulfillment_status"])
    if sequence[target_status] != sequence[current_status] + 1:
        raise HTTPException(
            status_code=409,
            detail="Fulfillment must move one step forward: Processing, Shipped, Delivered.",
        )

    connection.execute(
        """
        UPDATE sub_orders
        SET fulfillment_status = ?,
            admin_override_status = '',
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
            dispatched_at = CASE
                WHEN ? = 'SHIPPED' THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ELSE dispatched_at
            END,
            courier_name = CASE WHEN ? = '' THEN courier_name ELSE ? END,
            tracking_number = CASE WHEN ? = '' THEN tracking_number ELSE ? END
        WHERE id = ? AND seller_id = ?
        """,
        (
            target_status,
            target_status,
            courier_name,
            courier_name,
            tracking_number,
            tracking_number,
            sub_order_id,
            seller_id,
        ),
    )
    connection.execute(
        "UPDATE orders SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
        (row["parent_order_id"],),
    )
    display_status = FULFILLMENT_STATUS_LABELS.get(target_status, target_status)
    record_order_status_event(
        connection,
        row["parent_order_id"],
        sub_order_id,
        display_status,
        f"seller:{seller_id}",
    )
    return target_status, row["parent_order_id"]


def publish_order_update(
    request: Request,
    parent_order_id: int,
    sub_order_id: int,
    status: str,
) -> None:
    manager = getattr(request.app.state, "order_connections", None)
    if manager is None:
        return
    with get_connection() as connection:
        row = connection.execute(
            "SELECT tracking_id FROM orders WHERE id = ?", (parent_order_id,)
        ).fetchone()
    if row is not None and row["tracking_id"]:
        manager.publish(
            row["tracking_id"],
            {
                "type": "status",
                "status": status,
                "sub_order_id": sub_order_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
