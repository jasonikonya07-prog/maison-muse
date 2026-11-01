import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

MARKETPLACE_CATEGORIES = {
    "Agriculture & Livestock Farming",
    "Beauty & Personal Care Cosmetics",
    "Electronics & Consumer Hardware",
    "Fashion, Apparel & Footwear",
    "Home Improvement & Furniture",
    "FMCG & Groceries",
    "Healthcare & Pharmaceutical Supplies",
    "Automotive Parts & Heavy Equipment",
    "Veterinary Medicines",
    "Dairy Cattle",
    "Goats & Sheep",
    "Poultry & Fowl",
    "Beauty & Cosmetics",
    "Electronics",
    "Fashion & Clothing",
    "Home & Furniture",
    "Groceries & Food",
    "Phones & Accessories",
    "Baby & Kids",
    "Sports & Outdoors",
    "Automotive",
    "Agriculture & Garden",
    "Computers & Accessories",
    "Health & Personal Care",
    "Books & Stationery",
    "Kitchen & Dining",
    "Travel & Luggage",
    "Lighting & Electrical",
    "Pet Supplies",
    "Musical Instruments",
    "Perfumes & Fragrances",
    "Press-On Nails",
    "Skincare & Glow",
    "Lip & Makeup Essentials",
    "Hair & Accessories",
}
BUSINESS_TYPES = {
    "Agriculture & Livestock Farming",
    "Beauty & Personal Care Cosmetics",
    "Electronics & Consumer Hardware",
    "Fashion, Apparel & Footwear",
    "Home Improvement & Furniture",
    "FMCG & Groceries",
    "Healthcare & Pharmaceutical Supplies",
    "Automotive Parts & Heavy Equipment",
}
AGRICULTURE_BUSINESS_TYPE = "Agriculture & Livestock Farming"
AGRICULTURE_PRODUCT_CATEGORIES = {
    "Agriculture & Livestock",
    "Agriculture & Garden",
    "Veterinary Medicines",
    "Dairy Cattle",
    "Goats & Sheep",
    "Poultry & Fowl",
}


def _validate_phone_number(value: str, label: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValueError(f"Enter a valid {label} with 7–15 digits.")
    return value


def _validate_image_url(value: str) -> str:
    if not value:
        return value
    parsed = urlparse(value)
    local_http_host = parsed.hostname in {"localhost", "127.0.0.1", "testserver"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and local_http_host
    ):
        raise ValueError("Images must use HTTPS URLs or local development uploads.")
    return value


class CustomerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=4, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    address: str = Field(min_length=8, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        parts = value.split()
        if len(parts) < 2 or any(len(part) < 2 for part in parts):
            raise ValueError("Enter your first and last name.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid phone number with 7–15 digits.")
        return value

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Enter a complete delivery address.")
        return value


class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=99)
    variant: str = Field(default="", max_length=50)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: CustomerInfo
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)


class DemoCheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer: CustomerInfo
    items: list[OrderItemInput] = Field(min_length=1, max_length=50)
    city: str = Field(min_length=2, max_length=100)
    delivery_notes: str = Field(default="", max_length=500)
    mpesa_phone: str = Field(min_length=7, max_length=32)

    @field_validator("mpesa_phone")
    @classmethod
    def validate_mpesa_phone(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid M-Pesa phone number.")
        return value


class AuthRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=4, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["buyer", "seller"]
    phone: str = Field(min_length=7, max_length=32)
    store_name: str | None = Field(default=None, min_length=2, max_length=120)
    business_category: str | None = Field(
        default=None,
        validation_alias=AliasChoices("business_category", "store_category"),
    )
    business_type: str | None = Field(default=None, max_length=80)
    whatsapp_number: str = Field(default="", max_length=32)
    city: str | None = Field(default=None, max_length=100)
    payout_number: str | None = Field(default=None, min_length=3, max_length=120)
    business_registration_number: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        validation_alias=AliasChoices(
            "business_registration_number", "national_id"
        ),
    )
    accepted_terms: bool = False
    selected_plan: Literal["boutique", "pro", "enterprise"] | None = None

    @field_validator("full_name")
    @classmethod
    def validate_auth_full_name(cls, value: str) -> str:
        parts = value.split()
        if len(parts) < 2:
            raise ValueError("Enter your first and last name.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_auth_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("business_category")
    @classmethod
    def validate_auth_business_category(cls, value: str | None) -> str | None:
        if value is not None and value not in MARKETPLACE_CATEGORIES:
            raise ValueError("Choose one of the supported Maison Muse marketplace categories.")
        return value

    @field_validator("business_type")
    @classmethod
    def validate_auth_business_type(cls, value: str | None) -> str | None:
        if value is not None and value not in BUSINESS_TYPES:
            raise ValueError("Choose a supported primary industry.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_auth_phone(cls, value: str) -> str:
        return _validate_phone_number(value, "phone number")

    @field_validator("whatsapp_number")
    @classmethod
    def validate_auth_whatsapp_number(cls, value: str) -> str:
        return _validate_phone_number(value, "WhatsApp Business phone number") if value else value

    @model_validator(mode="after")
    def require_seller_auth_fields(self):
        if self.role == "seller" and any(
            not value
            for value in (
                self.store_name,
                self.business_category,
                self.business_type,
                self.payout_number,
                self.business_registration_number,
            )
        ):
            raise ValueError(
                "Store name, primary industry, business category, M-Pesa payout number, and registration number are required for sellers."
            )
        if self.role == "seller" and (not self.accepted_terms or not self.selected_plan):
            raise ValueError(
                "Seller terms must be accepted and a subscription plan must be selected."
            )
        if (
            self.role == "seller"
            and self.business_type == AGRICULTURE_BUSINESS_TYPE
            and not self.whatsapp_number
        ):
            raise ValueError(
                "A WhatsApp Business phone number is required for Agriculture & Livestock sellers."
            )
        return self


class AuthLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class GoogleAuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    credential: str = Field(default="", max_length=8192)
    simulation: bool = False

    @model_validator(mode="after")
    def require_credential_for_live_auth(self):
        if not self.simulation and len(self.credential) < 20:
            raise ValueError("A valid Google credential is required.")
        return self


class SellerRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    store_name: str = Field(min_length=2, max_length=120)
    owner_name: str = Field(min_length=2, max_length=120)
    logo_url: str = Field(default="", max_length=2048)
    banner_url: str = Field(default="", max_length=2048)
    business_phone: str = Field(min_length=7, max_length=32)
    payout_method: Literal["M-Pesa", "Bank"]
    payout_account: str = Field(min_length=3, max_length=120)
    business_type: str = Field(min_length=1, max_length=80)
    business_category: str = Field(default="Beauty & Personal Care Cosmetics", max_length=80)
    whatsapp_number: str = Field(default="", max_length=32)
    submitted_documents: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("business_type")
    @classmethod
    def validate_seller_business_type(cls, value: str) -> str:
        if value not in BUSINESS_TYPES:
            raise ValueError("Choose a supported primary industry.")
        return value

    @field_validator("business_category")
    @classmethod
    def validate_seller_business_category(cls, value: str) -> str:
        if value not in MARKETPLACE_CATEGORIES:
            raise ValueError("Choose a supported business category.")
        return value

    @field_validator("whatsapp_number")
    @classmethod
    def validate_seller_whatsapp_number(cls, value: str) -> str:
        return _validate_phone_number(value, "WhatsApp Business phone number") if value else value

    @model_validator(mode="after")
    def require_agriculture_whatsapp(self):
        if (
            self.business_type == AGRICULTURE_BUSINESS_TYPE
            and not self.whatsapp_number
        ):
            raise ValueError(
                "A WhatsApp Business phone number is required for Agriculture & Livestock sellers."
            )
        return self

    @field_validator("email")
    @classmethod
    def normalize_seller_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("logo_url", "banner_url")
    @classmethod
    def validate_optional_image_url(cls, value: str) -> str:
        if value and not value.startswith("https://"):
            raise ValueError("Store images must use HTTPS URLs.")
        return value

    @field_validator("submitted_documents")
    @classmethod
    def validate_seller_documents(cls, documents: list[str]) -> list[str]:
        if any(not document.startswith("https://") for document in documents):
            raise ValueError("Submitted documents must use HTTPS URLs.")
        return documents


class SellerLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SellerProductVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)
    options: list[str] = Field(min_length=1, max_length=20)


class SellerProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=160)
    brand: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    category: str = Field(min_length=2, max_length=80)
    detail: str = Field(min_length=5, max_length=240)
    description: str = Field(min_length=10, max_length=4000)
    price: float = Field(gt=0, le=1_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    lowStockThreshold: int = Field(default=5, ge=0, le=1_000_000)
    images: list[str] = Field(min_length=1, max_length=4)
    tags: list[str] = Field(default_factory=list, max_length=20)
    variants: list[SellerProductVariant] = Field(default_factory=list, max_length=20)
    status: Literal["ACTIVE", "DRAFT", "ARCHIVED"] = "ACTIVE"

    @field_validator("category")
    @classmethod
    def validate_product_category(cls, value: str) -> str:
        if value not in MARKETPLACE_CATEGORIES:
            raise ValueError("Choose one of the supported Maison Muse marketplace categories.")
        return value

    @field_validator("images")
    @classmethod
    def validate_seller_images(cls, images: list[str]) -> list[str]:
        return [_validate_image_url(image) for image in images]


class SellerProductBulkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["status", "discount", "out_of_stock"]
    status: Literal["ACTIVE", "DRAFT", "ARCHIVED"] | None = None
    discount_percent: int | None = Field(default=None, ge=1, le=90)

    @model_validator(mode="after")
    def validate_bulk_action(self):
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("Product IDs must be unique.")
        if self.action == "status" and self.status is None:
            raise ValueError("Choose a status for the selected products.")
        if self.action == "discount" and self.discount_percent is None:
            raise ValueError("Choose a discount percentage.")
        return self


class SellerFulfillmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal[
        "PROCESSING",
        "SHIPPED",
        "DELIVERED",
        "PENDING_PACKING",
        "PACKED_AND_READY",
        "DISPATCHED_TO_COURIER",
        "DELIVERED_TO_CUSTOMER",
    ]
    courier_name: str = Field(default="", max_length=100)
    tracking_number: str = Field(default="", max_length=120)


class AdminOrderOverrideUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal[
        "PENDING_PACKING",
        "PACKED",
        "DISPATCHED_TO_COURIER",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "CANCELLED",
    ]
    courier_name: str = Field(default="", max_length=100)
    tracking_number: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)


class SellerStorefrontUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    store_name: str = Field(min_length=2, max_length=120)
    business_category: str = Field(min_length=2, max_length=80)
    store_bio: str = Field(default="", max_length=1000)
    logo_url: str = Field(default="", max_length=2048)
    banner_url: str = Field(default="", max_length=2048)
    business_phone: str = Field(min_length=7, max_length=32)
    whatsapp_phone: str = Field(default="", max_length=32)
    instagram_url: str = Field(default="", max_length=2048)
    tiktok_url: str = Field(default="", max_length=2048)
    operating_hours: str = Field(default="", max_length=1000)
    holiday_mode: bool = False
    payout_method: Literal["M-Pesa", "Bank"]
    payout_account: str = Field(min_length=3, max_length=120)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("logo_url", "banner_url")
    @classmethod
    def validate_store_image_url(cls, value: str) -> str:
        return _validate_image_url(value)

    @field_validator("instagram_url", "tiktok_url")
    @classmethod
    def validate_social_url(cls, value: str) -> str:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Social links must be valid HTTP or HTTPS URLs.")
        return value

    @field_validator("business_category")
    @classmethod
    def validate_store_category(cls, value: str) -> str:
        if value not in MARKETPLACE_CATEGORIES:
            raise ValueError("Choose one of the supported Maison Muse marketplace categories.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_store_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class SellerPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_plan: Literal["boutique", "pro", "enterprise"]


class SellerPlanUpgrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_plan: Literal["boutique", "pro", "enterprise"]
    phone_number: str = Field(default="", max_length=32)


class SellerProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    new_email: str | None = Field(default=None, min_length=3, max_length=254)
    new_phone: str | None = Field(default=None, min_length=7, max_length=32)

    @field_validator("new_email")
    @classmethod
    def normalize_new_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("new_phone")
    @classmethod
    def validate_new_phone(cls, value: str | None) -> str | None:
        if value is not None and not 7 <= len(re.sub(r"\D", "", value)) <= 15:
            raise ValueError("Enter a valid phone number.")
        return value


class SellerProfileUpdateVerify(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=r"^\d{6}$")


class SellerPromotionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    promotion_type: Literal["flash_sale", "coupon", "price_discount"]
    name: str = Field(min_length=2, max_length=100)
    product_ids: list[str] = Field(min_length=1, max_length=100)
    discount_percent: int = Field(ge=1, le=90)
    code: str = Field(default="", max_length=32, pattern=r"^[A-Za-z0-9_-]*$")
    usage_limit: int = Field(default=0, ge=0, le=1_000_000)
    expires_at: datetime

    @model_validator(mode="after")
    def validate_promotion(self):
        if self.expires_at.tzinfo is None:
            self.expires_at = self.expires_at.replace(tzinfo=timezone.utc)
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("Product IDs must be unique.")
        if self.promotion_type == "coupon" and len(self.code) < 3:
            raise ValueError("Coupon codes must have at least three characters.")
        if self.promotion_type != "coupon" and self.code:
            raise ValueError("Only coupon promotions can have a redemption code.")
        if self.expires_at <= datetime.now(timezone.utc):
            raise ValueError("Promotion expiry must be in the future.")
        return self


class SellerCampaignEnrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_enrollment_products(self):
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("Product IDs must be unique.")
        return self


class SellerReturnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sub_order_id: int = Field(gt=0)
    order_number: str = Field(min_length=4, max_length=80)
    customer_phone: str = Field(min_length=7, max_length=32)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("customer_phone")
    @classmethod
    def validate_return_phone(cls, value: str) -> str:
        if not 7 <= len(re.sub(r"\D", "", value)) <= 15:
            raise ValueError("Enter the phone number used for this order.")
        return value


class SellerReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["refund_approved", "replacement_offered", "escalated", "closed"]
    resolution_note: str = Field(default="", max_length=1000)
    evidence: str = Field(default="", max_length=2048)


class SellerAdBoostInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    duration_days: int = Field(default=3, ge=1, le=30)
    amount: float = Field(default=500, ge=500, le=1_000_000)


class SellerTeamInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(default="", max_length=120)
    role: Literal["Inventory Clerk", "Fulfillment Manager", "Accountant"]

    @field_validator("email")
    @classmethod
    def normalize_team_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid team member email.")
        return normalized


class SellerTeamMemberStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "REVOKED"]


class SellerBuyerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: str = Field(min_length=1, max_length=100)
    customer_name: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=2000)


class SellerBuyerReply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=2000)


class SellerMessageReply(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(min_length=10, max_length=80)
    body: str = Field(min_length=1, max_length=2000)


class SellerNotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_stock_sms: bool = False
    low_stock_whatsapp: bool = False
    incoming_orders_sms: bool = False
    incoming_orders_whatsapp: bool = False


class SellerFulfillmentModeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fulfillment_mode: Literal["SELF_FULFILLMENT", "MAISON_EXPRESS"]


class SellerManifestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=100_000)


class SellerDropoffManifestInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hub_name: str = Field(min_length=2, max_length=120)
    items: list[SellerManifestItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_manifest_items(self):
        ids = [item.product_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Each product may only appear once in the manifest.")
        return self


class SellerVasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    service_type: Literal["BACKGROUND_CLEANUP", "SEO_ENHANCEMENT"]


class SellerQcReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["APPROVE", "REJECT"]
    notes: str = Field(default="", max_length=1000)


class SellerRepricingRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_price: float = Field(gt=0, le=1_000_000)
    max_price: float = Field(gt=0, le=1_000_000)
    rule: Literal["CLEARANCE_DISCOUNT", "MATCH_LOWEST_MARKET_PRICE"]

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.max_price < self.min_price:
            raise ValueError("Maximum price must be greater than or equal to minimum price.")
        return self


class SellerBranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=5, max_length=300)
    city: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=32)


class SellerBranchInventoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=0, le=1_000_000)


class SellerBranchInventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SellerBranchInventoryItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_branch_products(self):
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("Each product may only appear once in an allocation.")
        return self


class SellerReviewRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["EMAIL", "SMS"]


class SellerRestockRecommendationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_quantity: int = Field(gt=0, le=1_000_000)


class SellerStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PENDING", "APPROVED", "SUSPENDED"]


class SellerReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal[
        "APPROVE", "REJECT", "REQUEST_INFO", "SUSPEND", "UNDER_AUDIT", "RESTORE"
    ]
    reason: str = Field(default="", max_length=1000)

    @field_validator("reason")
    @classmethod
    def require_review_reason(cls, value: str, info) -> str:
        if info.data.get("action") in {
            "REJECT",
            "REQUEST_INFO",
            "SUSPEND",
            "UNDER_AUDIT",
        } and len(value) < 3:
            raise ValueError("Provide a reason for this seller review action.")
        return value


class CommissionSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_percentage: float = Field(ge=0, le=100)
    category_rates: dict[str, float] = Field(default_factory=dict)
    seller_rates: dict[int, float] = Field(default_factory=dict)
    seller_category_rates: dict[int, dict[str, float]] = Field(default_factory=dict)

    @field_validator("category_rates")
    @classmethod
    def validate_category_rates(cls, value: dict[str, float]) -> dict[str, float]:
        allowed = {
            "Perfumes & Fragrances",
            "Press-On Nails",
            "Skincare & Glow",
            "Lip & Makeup Essentials",
            "Hair & Accessories",
        }
        if set(value) - allowed or any(not 0 <= rate <= 100 for rate in value.values()):
            raise ValueError("Commission category rates must use a supported category and be between 0 and 100.")
        return value

    @field_validator("seller_rates")
    @classmethod
    def validate_seller_rates(cls, value: dict[int, float]) -> dict[int, float]:
        if any(seller_id <= 0 or not 0 <= rate <= 100 for seller_id, rate in value.items()):
            raise ValueError("Seller commission rates must be between 0 and 100.")
        return value

    @field_validator("seller_category_rates")
    @classmethod
    def validate_seller_category_rates(
        cls, value: dict[int, dict[str, float]]
    ) -> dict[int, dict[str, float]]:
        allowed = {
            "Perfumes & Fragrances",
            "Press-On Nails",
            "Skincare & Glow",
            "Lip & Makeup Essentials",
            "Hair & Accessories",
        }
        if any(
            seller_id <= 0
            or set(rates) - allowed
            or any(not 0 <= rate <= 100 for rate in rates.values())
            for seller_id, rates in value.items()
        ):
            raise ValueError("Seller/category commission rates are invalid.")
        return value


class SellerPayoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    seller_id: int = Field(gt=0)
    sub_order_ids: list[int] = Field(min_length=1, max_length=100)
    reference: str = Field(min_length=2, max_length=120)

    @field_validator("sub_order_ids")
    @classmethod
    def validate_unique_sub_orders(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("A seller order may only be paid once per transaction.")
        return value


class SellerWithdrawalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    amount: float = Field(ge=1, le=100_000_000)
    destination_type: Literal["registered_phone", "paybill", "till"]
    destination: str = Field(default="", max_length=120)

    @field_validator("destination")
    @classmethod
    def validate_payout_destination(cls, value: str, info) -> str:
        if not value:
            return value
        digits = re.sub(r"\D", "", value)
        minimum = 5 if info.data.get("destination_type") in {"paybill", "till"} else 7
        if not minimum <= len(digits) <= 15:
            raise ValueError("Enter a valid payout phone, Paybill, or Till number.")
        return digits

    @model_validator(mode="after")
    def validate_destination(self):
        if self.destination_type == "registered_phone":
            if self.destination:
                raise ValueError("The registered payout destination is selected automatically.")
        elif not self.destination:
            raise ValueError("Enter the Paybill or Till number.")
        return self


class MarketplacePayoutUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["COMPLETED", "FAILED", "PROCESSING"]
    transaction_id: str = Field(default="", max_length=120)
    failure_reason: str = Field(default="", max_length=500)

    @field_validator("failure_reason")
    @classmethod
    def require_payout_failure_reason(cls, value: str, info) -> str:
        if info.data.get("status") == "FAILED" and len(value) < 3:
            raise ValueError("Provide a reason for a failed payout.")
        return value


class MarketplaceDisputeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal[
        "REFUND_REQUESTED",
        "REFUND_RECORDED",
        "PENALTY_RECORDED",
        "RETURN_ACCEPTED",
        "RETURN_REJECTED",
    ]
    reason: str = Field(min_length=3, max_length=1000)
    amount: float = Field(default=0, ge=0, le=100_000_000)


class AdminLogin(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ProductAdminInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=160)
    brand: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    category: Literal[
        "Perfumes & Fragrances",
        "Press-On Nails",
        "Skincare & Glow",
        "Lip & Makeup Essentials",
        "Hair & Accessories",
    ]
    detail: str = Field(min_length=5, max_length=240)
    description: str = Field(min_length=10, max_length=4000)
    price: float = Field(gt=0, le=1_000_000)
    unitCost: float = Field(default=0, ge=0, le=1_000_000)
    oldPrice: float | None = Field(default=None, gt=0, le=1_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    lowStockThreshold: int = Field(default=5, ge=0, le=1_000_000)
    rating: float = Field(default=0, ge=0, le=5)
    reviewsCount: int = Field(default=0, ge=0)
    tag: str = Field(default="NEW ARRIVAL", max_length=50)
    tagColor: str = Field(default="bg-rose-600", max_length=40)
    images: list[str] = Field(min_length=1, max_length=8)
    details: dict[str, Any] = Field(default_factory=dict)
    active: bool = True

    @field_validator("images")
    @classmethod
    def validate_images(cls, images: list[str]) -> list[str]:
        for image in images:
            if not image.startswith("https://"):
                raise ValueError("Product images must use HTTPS URLs.")
        return images

    @field_validator("details")
    @classmethod
    def validate_details(cls, details: dict[str, Any]) -> dict[str, Any]:
        if len(details) > 24 or any(len(str(value)) > 500 for value in details.values()):
            raise ValueError("Product details exceed the allowed limits.")
        return details


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "processing", "shipped", "delivered", "cancelled"]


class StoreSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_status: Literal["live", "maintenance"]


class CampaignInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=120)
    discount_percent: int = Field(ge=1, le=90)
    stock_allocation: int = Field(ge=0, le=1_000_000)
    duration_minutes: int = Field(ge=1, le=10080)


class RolePermissionsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: dict[str, dict[str, bool]]

    @field_validator("permissions")
    @classmethod
    def validate_permissions(
        cls, value: dict[str, dict[str, bool]]
    ) -> dict[str, dict[str, bool]]:
        expected_areas = {"products", "orders", "analytics", "settings"}
        expected_rights = {"read", "write", "delete"}
        for area, rights in value.items():
            if area not in expected_areas or set(rights) != expected_rights:
                raise ValueError("Permissions must define read, write, and delete for each supported area.")
        if set(value) != expected_areas:
            raise ValueError("Permissions must define every supported area.")
        if not all(
            isinstance(allowed, bool)
            for rights in value.values()
            for allowed in rights.values()
        ):
            raise ValueError("Permission values must be boolean.")
        return value


class ProductCostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_cost: float = Field(ge=0, le=1_000_000)


class PurchaseOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=1_000_000)


class NewsletterSignup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized
