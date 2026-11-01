import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status

from app.database import get_connection


SANDBOX_BASE_URL = "https://cybqa.pesapal.com/pesapalv3"
LIVE_BASE_URL = "https://pay.pesapal.com/v3"


class PesapalError(Exception):
    pass


@dataclass(frozen=True)
class PesapalConfig:
    base_url: str
    consumer_key: str
    consumer_secret: str
    callback_url: str
    ipn_url: str
    ipn_id: str


def get_config(*, require_ipn_id: bool = True) -> PesapalConfig:
    environment = os.getenv("PESAPAL_ENVIRONMENT", "sandbox").strip().casefold()
    if environment not in {"sandbox", "live"}:
        raise PesapalError("PESAPAL_ENVIRONMENT must be 'sandbox' or 'live'.")

    consumer_key = os.getenv("PESAPAL_CONSUMER_KEY", "").strip()
    consumer_secret = os.getenv("PESAPAL_CONSUMER_SECRET", "").strip()
    callback_url = os.getenv("PESAPAL_CALLBACK_URL", "").strip()
    ipn_url = os.getenv("PESAPAL_IPN_URL", "").strip()
    ipn_id = os.getenv("PESAPAL_IPN_ID", "").strip()
    missing = [
        name
        for name, value in (
            ("PESAPAL_CONSUMER_KEY", consumer_key),
            ("PESAPAL_CONSUMER_SECRET", consumer_secret),
            ("PESAPAL_CALLBACK_URL", callback_url),
            ("PESAPAL_IPN_URL", ipn_url),
            *([("PESAPAL_IPN_ID", ipn_id)] if require_ipn_id else []),
        )
        if not value
    ]
    if missing:
        raise PesapalError(f"Configure the required Pesapal settings: {', '.join(missing)}.")

    for name, value in (("PESAPAL_CALLBACK_URL", callback_url), ("PESAPAL_IPN_URL", ipn_url)):
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise PesapalError(f"{name} must be an absolute HTTP or HTTPS URL.")
        if environment == "live" and parsed.scheme != "https":
            raise PesapalError(f"{name} must use HTTPS in the live environment.")

    return PesapalConfig(
        base_url=SANDBOX_BASE_URL if environment == "sandbox" else LIVE_BASE_URL,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        callback_url=callback_url,
        ipn_url=ipn_url,
        ipn_id=ipn_id,
    )


def is_configured() -> bool:
    try:
        get_config()
    except PesapalError:
        return False
    return True


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    token: str | None = None,
    params: dict | None = None,
) -> dict:
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = client.request(
                method,
                url,
                json=payload,
                params=params,
                headers=headers,
            )
    except httpx.TimeoutException as error:
        raise PesapalError("Pesapal did not respond before the request timed out.") from error
    except httpx.RequestError as error:
        raise PesapalError("Could not connect to Pesapal.") from error

    try:
        response_data = response.json()
    except ValueError as error:
        raise PesapalError("Pesapal returned an invalid response.") from error

    if not response.is_success or not isinstance(response_data, dict):
        raise PesapalError("Pesapal rejected the payment request.")
    if response_data.get("error"):
        raise PesapalError("Pesapal rejected the payment request.")
    return response_data


def get_access_token(config: PesapalConfig) -> str:
    response = _request_json(
        "POST",
        f"{config.base_url}/api/Auth/RequestToken",
        payload={
            "consumer_key": config.consumer_key,
            "consumer_secret": config.consumer_secret,
        },
    )
    token = response.get("token")
    if not isinstance(token, str) or not token:
        raise PesapalError("Pesapal did not issue an access token.")
    return token


def register_ipn_url() -> str:
    config = get_config(require_ipn_id=False)
    token = get_access_token(config)
    response = _request_json(
        "POST",
        f"{config.base_url}/api/URLSetup/RegisterIPN",
        token=token,
        payload={"url": config.ipn_url, "ipn_notification_type": "GET"},
    )
    ipn_id = response.get("ipn_id")
    if not isinstance(ipn_id, str) or not ipn_id:
        raise PesapalError("Pesapal did not return a registered IPN ID.")
    return ipn_id


def submit_order(
    *,
    order_number: str,
    amount_cents: int,
    customer_name: str,
    phone_number: str,
    delivery_address: str,
) -> dict:
    config = get_config()
    token = get_access_token(config)
    name_parts = customer_name.split()
    first_name = name_parts[0]
    last_name = name_parts[-1] if len(name_parts) > 1 else first_name
    middle_name = " ".join(name_parts[1:-1])
    response = _request_json(
        "POST",
        f"{config.base_url}/api/Transactions/SubmitOrderRequest",
        token=token,
        payload={
            "id": order_number,
            "currency": "KES",
            "amount": float(Decimal(amount_cents) / 100),
            "description": f"Maison Muse order {order_number}",
            "callback_url": config.callback_url,
            "notification_id": config.ipn_id,
            "billing_address": {
                "phone_number": phone_number,
                "country_code": "KE",
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
                "line_1": delivery_address,
            },
        },
    )
    tracking_id = response.get("order_tracking_id")
    merchant_reference = response.get("merchant_reference")
    redirect_url = response.get("redirect_url")
    parsed_redirect = urlparse(redirect_url) if isinstance(redirect_url, str) else None
    if (
        not isinstance(tracking_id, str)
        or not tracking_id
        or merchant_reference != order_number
        or parsed_redirect is None
        or parsed_redirect.scheme != "https"
        or parsed_redirect.hostname != urlparse(config.base_url).hostname
    ):
        raise PesapalError("Pesapal returned incomplete payment instructions.")
    return {
        "tracking_id": tracking_id,
        "merchant_reference": merchant_reference,
        "redirect_url": redirect_url,
    }


def refresh_order_payment(order_number: str, tracking_id: str) -> dict:
    with get_connection() as connection:
        order = connection.execute(
            """
            SELECT order_number, payment_status, gateway_tracking_id, total_cents
            FROM orders WHERE order_number = ?
            """,
            (order_number,),
        ).fetchone()
    if order is None or order["gateway_tracking_id"] != tracking_id:
        raise HTTPException(status_code=404, detail="Payment reference was not found.")

    try:
        config = get_config()
        token = get_access_token(config)
        provider_status = _request_json(
            "GET",
            f"{config.base_url}/api/Transactions/GetTransactionStatus",
            token=token,
            params={"orderTrackingId": tracking_id},
        )
    except PesapalError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if "Configure the required Pesapal settings" in str(error)
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=f"Could not verify this payment with Pesapal: {error}",
        ) from error

    reference = provider_status.get("merchant_reference")
    if reference != order_number:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The payment reference does not match this order.",
        )
    currency = provider_status.get("currency")
    if not isinstance(currency, str) or currency.upper() != "KES":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The payment currency does not match this order.",
        )
    try:
        amount_cents = int(
            (Decimal(str(provider_status["amount"])) * 100).quantize(Decimal("1"))
        )
    except (KeyError, InvalidOperation, ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Pesapal returned a payment amount that could not be verified.",
        ) from error
    if amount_cents != order["total_cents"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The verified payment amount does not match this order.",
        )

    provider_description = str(
        provider_status.get("payment_status_description", "")
    ).strip()
    normalized_status = provider_description.casefold()
    if normalized_status == "completed":
        payment_status = "paid"
    elif normalized_status in {"failed", "invalid"}:
        payment_status = "failed"
    elif normalized_status == "reversed":
        payment_status = "reversed"
    elif normalized_status == "processing":
        payment_status = "processing"
    else:
        payment_status = "pending_callback"

    gateway_reference = str(provider_status.get("confirmation_code") or "")
    with get_connection() as connection:
        current = connection.execute(
            """
            SELECT payment_status, gateway_reference, gateway_status
            FROM orders WHERE order_number = ?
            """,
            (order_number,),
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        if current["payment_status"] != "paid" or payment_status == "reversed":
            gateway_reference = gateway_reference or current["gateway_reference"]
            connection.execute(
                """
                UPDATE orders
                SET payment_status = ?, gateway_status = ?, gateway_reference = ?
                WHERE order_number = ?
                """,
                (payment_status, provider_description, gateway_reference, order_number),
            )
            connection.commit()
        else:
            payment_status = "paid"
            provider_description = current["gateway_status"] or provider_description

    return {
        "order_number": order_number,
        "payment_status": payment_status,
        "provider_status": provider_description or "Pending",
    }
