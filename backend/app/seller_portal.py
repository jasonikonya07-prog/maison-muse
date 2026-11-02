from typing import Any

from fastapi import HTTPException, status

from app.database import get_connection


ENABLED_SETTING = "seller_portal_maintenance_enabled"
REASON_SETTING = "seller_portal_maintenance_reason"


def get_seller_portal_maintenance(connection: Any | None = None) -> dict[str, Any]:
    if connection is None:
        with get_connection() as active_connection:
            return get_seller_portal_maintenance(active_connection)
    rows = connection.execute(
        """
        SELECT key, value FROM store_settings
        WHERE key IN (?, ?)
        """,
        (ENABLED_SETTING, REASON_SETTING),
    ).fetchall()
    settings = {row["key"]: row["value"] for row in rows}
    return {
        "enabled": settings.get(ENABLED_SETTING) == "true",
        "reason": settings.get(REASON_SETTING, ""),
    }


def ensure_seller_portal_open(connection: Any | None = None) -> None:
    maintenance = get_seller_portal_maintenance(connection)
    if maintenance["enabled"]:
        reason = maintenance["reason"]
        detail = "The Seller Portal is temporarily under maintenance."
        if reason:
            detail = f"{detail} Reason: {reason}"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
