from fastapi import APIRouter, HTTPException, Query

from app.pesapal import refresh_order_payment


router = APIRouter()


@router.get("/payments/pesapal/status")
def pesapal_payment_status(
    order_tracking_id: str = Query(min_length=1, max_length=100),
    merchant_reference: str = Query(min_length=1, max_length=100),
) -> dict:
    return refresh_order_payment(merchant_reference, order_tracking_id)


@router.get("/payments/pesapal/ipn")
def pesapal_ipn(
    notification_type: str = Query(alias="OrderNotificationType", min_length=1),
    tracking_id: str = Query(alias="OrderTrackingId", min_length=1, max_length=100),
    merchant_reference: str = Query(
        alias="OrderMerchantReference",
        min_length=1,
        max_length=100,
    ),
) -> dict:
    refresh_order_payment(merchant_reference, tracking_id)
    return {
        "orderNotificationType": notification_type,
        "orderTrackingId": tracking_id,
        "orderMerchantReference": merchant_reference,
        "status": 200,
    }
