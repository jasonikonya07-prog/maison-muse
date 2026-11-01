import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.database import decode_json_array, get_connection
from app.schemas import AGRICULTURE_PRODUCT_CATEGORIES


router = APIRouter()
CATEGORY_NAME_ALIASES = {
    "beauty-cosmetics": (
        "Perfumes & Fragrances",
        "Press-On Nails",
        "Skincare & Glow",
        "Lip & Makeup Essentials",
        "Hair & Accessories",
    ),
    "agriculture-livestock": (
        "Agriculture & Livestock",
        "Agriculture & Garden",
        "Veterinary Medicines",
        "Dairy Cattle",
        "Goats & Sheep",
        "Poultry & Fowl",
    ),
}
def expire_seller_promotions(connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    expired_rows = connection.execute(
        """
        SELECT id, product_ids_json FROM seller_promotions
        WHERE status = 'ACTIVE' AND promotion_type IN ('flash_sale', 'price_discount')
          AND expires_at <= ?
        """,
        (now,),
    ).fetchall()
    if not expired_rows:
        return
    product_ids = {
        product_id
        for promotion in expired_rows
        for product_id in json.loads(promotion["product_ids_json"] or "[]")
    }
    connection.execute(
        """
        UPDATE seller_promotions SET status = 'EXPIRED'
        WHERE status = 'ACTIVE' AND promotion_type IN ('flash_sale', 'price_discount')
          AND expires_at <= ?
        """,
        (now,),
    )
    for product_id in product_ids:
        connection.execute(
            """
            UPDATE products
            SET price = COALESCE(old_price, price), old_price = NULL, discount = ''
            WHERE id = ?
            """,
            (product_id,),
        )
    connection.commit()


def serialize_product(row, include_internal: bool = False) -> dict:
    images = decode_json_array(row["gallery_json"])
    row_keys = set(row.keys())
    linked_seller_name = row["linked_seller_name"] if "linked_seller_name" in row_keys else ""
    seller_name = linked_seller_name or (
        row["seller_name"] if "seller_name" in row_keys else ""
    )
    seller_slug = (
        row["linked_seller_slug"] if "linked_seller_slug" in row_keys else ""
    ) or (row["seller_slug"] if "seller_slug" in row_keys else "")
    seller_phone = (
        row["linked_seller_phone"] if "linked_seller_phone" in row_keys else ""
    ) or (row["seller_phone"] if "seller_phone" in row_keys else "")
    farmer_whatsapp = (
        row["linked_farmer_whatsapp_number"]
        if "linked_farmer_whatsapp_number" in row_keys
        else ""
    ) or (
        row["farmer_whatsapp"] if "farmer_whatsapp" in row_keys else ""
    ) or (
        row["seller_whatsapp_phone"] if "seller_whatsapp_phone" in row_keys else ""
    ) or (
        row["linked_seller_whatsapp_phone"]
        if "linked_seller_whatsapp_phone" in row_keys
        else ""
    )
    farmer_name = (
        row["farmer_name"] if "farmer_name" in row_keys else ""
    ) or linked_seller_name or seller_name
    linked_business_type = (
        row["linked_business_type"] if "linked_business_type" in row_keys else ""
    )
    is_agri_product = bool(
        (row["is_agri_product"] if "is_agri_product" in row_keys else False)
        or linked_business_type == "Agriculture & Livestock Farming"
        or (row["category"] in AGRICULTURE_PRODUCT_CATEGORIES)
    )
    seller_verified = (
        bool(row["linked_seller_verified"])
        if "linked_seller_verified" in row_keys and row["linked_seller_name"]
        else bool(row["seller_verified"])
        if "seller_verified" in row_keys
        else bool(seller_name)
    )
    seller = None
    if seller_name:
        seller = {
            "id": row["seller_id"],
            "storeName": seller_name,
            "storeSlug": seller_slug,
            "rating": row["seller_rating"] if "seller_rating" in row_keys else 0,
            "logoUrl": row["seller_logo"] if "seller_logo" in row_keys else "",
            "businessPhone": seller_phone,
            "whatsappPhone": farmer_whatsapp or (
                row["linked_seller_whatsapp_phone"]
                if "linked_seller_whatsapp_phone" in row_keys
                else ""
            ) or (
                row["seller_whatsapp_phone"]
                if "seller_whatsapp_phone" in row_keys
                else ""
            ),
            "verified": seller_verified,
            "holidayMode": bool(row["seller_holiday_mode"])
            if "seller_holiday_mode" in row_keys
            else False,
        }
    image = row["image_url"] if "image_url" in row_keys and row["image_url"] else row["image"]
    title = row["title"] if "title" in row_keys and row["title"] else row["name"]
    features = (
        json.loads(row["features_json"])
        if "features_json" in row_keys and row["features_json"]
        else []
    )
    boosted_until = row["boosted_until"] if "boosted_until" in row_keys else ""
    sponsored = bool(
        boosted_until
        and boosted_until > datetime.now(timezone.utc).isoformat()
    )
    result = {
        "id": row["id"],
        "name": title,
        "title": title,
        "slug": row["slug"] if "slug" in row_keys else "",
        "brand": row["brand"],
        "sku": row["sku"],
        "category": row["category"],
        "category_slug": row["category_slug"] if "category_slug" in row_keys else "",
        "sub_category": row["sub_category"] if "sub_category" in row_keys else "",
        "detail": row["detail"],
        "price": row["price"],
        "oldPrice": row["old_price"],
        "discount": row["discount"],
        "rating": row["rating"],
        "reviewsCount": row["reviews_count"],
        "tag": "SPONSORED" if sponsored else row["tag"],
        "tagColor": row["tag_color"],
        "description": row["description"],
        "stock": row["stock"],
        "stock_status": (
            "OUT_OF_STOCK"
            if row["stock"] <= 0
            else "LOW_STOCK"
            if row["stock"] < 5
            else "IN_STOCK"
        ),
        "lowStockThreshold": row["low_stock_threshold"],
        "inStock": row["stock"] > 0,
        "image": image,
        "image_url": image,
        "features": features,
        "sponsored": sponsored,
        "boosted_until": boosted_until,
        "gallery": images,
        "images": images,
        "tags": decode_json_array(row["tags_json"]) if "tags_json" in row_keys else [],
        "variants": json.loads(row["variants_json"]) if "variants_json" in row_keys else [],
        "status": row["product_status"] if "product_status" in row_keys else "ACTIVE",
        "notes": decode_json_array(row["notes_json"]),
        "nailSizes": decode_json_array(row["nail_sizes_json"]),
        "highlights": decode_json_array(row["highlights_json"]),
        "details": json.loads(row["details_json"]),
        "tone": row["tone"],
        "seller": seller,
        "sellerId": row["seller_id"] if "seller_id" in row_keys else None,
        "seller_name": seller_name or None,
        "seller_slug": seller_slug or None,
        "seller_phone": seller_phone or None,
        "seller_whatsapp_phone": (
            row["seller_whatsapp_phone"]
            if "seller_whatsapp_phone" in row_keys
            else None
        ),
        "seller_verified": seller_verified,
        "is_agri_product": is_agri_product,
        "farmer_name": farmer_name or None,
        "farmer_whatsapp": farmer_whatsapp or None,
        "farmerName": farmer_name or None,
        "farmerWhatsApp": farmer_whatsapp or None,
    }
    if include_internal:
        result["unitCost"] = row["unit_cost"]
    if "qc_status" in row_keys:
        result["qc_status"] = row["qc_status"]
    return result


@router.get("/products")
def list_products(
    search: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=60),
    deals: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions = []
    parameters: list[object] = []
    normalized_search = search.strip()
    normalized_category = category.strip()
    if normalized_search:
        conditions.append(
            "lower(name || ' ' || brand || ' ' || detail || ' ' || category || ' ' || description) LIKE lower(?)"
        )
        parameters.append(f"%{normalized_search}%")
    if normalized_category and normalized_category.casefold() != "all":
        category_values = [value.strip() for value in normalized_category.split(",") if value.strip()]
        if category_values:
            category_names = list(dict.fromkeys(
                name.casefold()
                for value in category_values
                for name in (value, *CATEGORY_NAME_ALIASES.get(value.casefold(), ()))
            ))
            slug_placeholders = ",".join("?" for _ in category_values)
            name_placeholders = ",".join("?" for _ in category_names)
            conditions.append(
                f"""(
                    lower(p.category_slug) IN ({slug_placeholders})
                    OR lower(p.category) IN ({name_placeholders})
                    OR lower(p.category) IN (
                        SELECT lower(c.name) FROM categories c
                        WHERE lower(c.slug) IN ({slug_placeholders})
                    )
                )"""
            )
            parameters.extend(category_values)
            parameters.extend(category_names)
            parameters.extend(category_values)
    conditions.append("p.active = 1 AND p.product_status = 'ACTIVE'")
    conditions.append("(p.seller_id IS NULL OR (s.status = 'APPROVED' AND s.review_state = 'CLEAR' AND s.maintenance_mode = 0))")
    if deals:
        conditions.append(
            "(COALESCE(p.old_price, 0) > p.price OR trim(COALESCE(p.discount, '')) != '')"
        )
    where_clause = f"WHERE {' AND '.join(conditions)}"
    parameters.extend([limit, offset])

    with get_connection() as connection:
        expire_seller_promotions(connection)
        rows = connection.execute(
            f"""
            SELECT p.*, s.store_name AS linked_seller_name,
                   s.store_slug AS linked_seller_slug,
                   s.rating AS seller_rating, s.logo_url AS seller_logo,
                   s.business_phone AS linked_seller_phone,
                   s.whatsapp_phone AS linked_seller_whatsapp_phone,
                   s.whatsapp_number AS linked_farmer_whatsapp_number,
                   s.business_type AS linked_business_type,
                   s.status = 'APPROVED' AND s.review_state = 'CLEAR' AS linked_seller_verified,
                   s.holiday_mode AS seller_holiday_mode
            FROM products p
            LEFT JOIN sellers s ON s.id = p.seller_id
            {where_clause}
            ORDER BY CASE
                WHEN p.boosted_until != ''
                  AND p.boosted_until > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                THEN 0 ELSE 1 END,
                p.category, p.name
            LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
    return [serialize_product(row) for row in rows]


@router.get("/categories")
def list_catalog_categories() -> list[dict]:
    with get_connection() as connection:
        expire_seller_promotions(connection)
        roots = connection.execute(
            """
            SELECT c.id, c.name, c.slug, c.parent_id, c.icon_name,
                   COUNT(DISTINCT p.id) AS product_count
            FROM categories c
            LEFT JOIN products p
              ON p.category_slug = c.slug
             AND p.active = 1 AND p.product_status = 'ACTIVE'
            WHERE c.parent_id IS NULL
            GROUP BY c.id
            ORDER BY c.id
            """
        ).fetchall()
        categories = []
        for root in roots:
            children = connection.execute(
                """
                SELECT child.id, child.name, child.slug, child.parent_id,
                       child.icon_name, COUNT(DISTINCT p.id) AS product_count
                FROM categories child
                LEFT JOIN products p
                  ON p.sub_category = child.name
                 AND p.category_slug = ?
                 AND p.active = 1 AND p.product_status = 'ACTIVE'
                WHERE child.parent_id = ?
                GROUP BY child.id
                ORDER BY child.id
                """,
                (root["slug"], root["id"]),
            ).fetchall()
            categories.append(
                {
                    **dict(root),
                    "subcategories": [dict(child) for child in children],
                }
            )
    return categories


@router.get("/products/category/{category_slug}")
def list_products_by_category(
    category_slug: str,
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    conditions = [
        "p.active = 1 AND p.product_status = 'ACTIVE'",
        "(p.seller_id IS NULL OR (s.status = 'APPROVED' AND s.review_state = 'CLEAR' AND s.maintenance_mode = 0))",
        "(lower(p.category_slug) = lower(?) OR EXISTS (SELECT 1 FROM categories c WHERE c.slug = lower(?) AND lower(c.name) = lower(p.category)))",
    ]
    parameters: list[object] = [category_slug, category_slug]
    normalized_search = search.strip()
    if normalized_search:
        conditions.append(
            "lower(p.name || ' ' || p.brand || ' ' || p.detail || ' ' || p.category || ' ' || p.description) LIKE lower(?)"
        )
        parameters.append(f"%{normalized_search}%")
    parameters.extend([limit, offset])

    with get_connection() as connection:
        expire_seller_promotions(connection)
        rows = connection.execute(
            f"""
            SELECT p.*, s.store_name AS linked_seller_name,
                   s.store_slug AS linked_seller_slug,
                   s.rating AS seller_rating, s.logo_url AS seller_logo,
                   s.business_phone AS linked_seller_phone,
                   s.whatsapp_phone AS linked_seller_whatsapp_phone,
                   s.whatsapp_number AS linked_farmer_whatsapp_number,
                   s.business_type AS linked_business_type,
                   s.status = 'APPROVED' AND s.review_state = 'CLEAR' AS linked_seller_verified,
                   s.holiday_mode AS seller_holiday_mode
            FROM products p
            LEFT JOIN sellers s ON s.id = p.seller_id
            WHERE {' AND '.join(conditions)}
            ORDER BY p.name
            LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
    return [serialize_product(row) for row in rows]


@router.get("/products/categories")
def list_categories() -> list[str]:
    with get_connection() as connection:
        expire_seller_promotions(connection)
        rows = connection.execute(
            """
            SELECT DISTINCT p.category FROM products p
            LEFT JOIN sellers s ON s.id = p.seller_id
            WHERE p.active = 1 AND p.product_status = 'ACTIVE'
              AND (p.seller_id IS NULL OR (s.status = 'APPROVED' AND s.review_state = 'CLEAR' AND s.maintenance_mode = 0))
            ORDER BY p.category
            """
        ).fetchall()
    return [row["category"] for row in rows]


@router.get("/products/{product_id}")
def get_product(product_id: str) -> dict:
    with get_connection() as connection:
        expire_seller_promotions(connection)
        row = connection.execute(
            """
            SELECT p.*, s.store_name AS linked_seller_name,
                   s.store_slug AS linked_seller_slug,
                   s.rating AS seller_rating, s.logo_url AS seller_logo,
                   s.business_phone AS linked_seller_phone,
                   s.whatsapp_phone AS linked_seller_whatsapp_phone,
                   s.whatsapp_number AS linked_farmer_whatsapp_number,
                   s.business_type AS linked_business_type,
                   s.status = 'APPROVED' AND s.review_state = 'CLEAR' AS linked_seller_verified,
                   s.holiday_mode AS seller_holiday_mode
            FROM products p
            LEFT JOIN sellers s ON s.id = p.seller_id
            WHERE p.id = ? AND p.active = 1 AND p.product_status = 'ACTIVE'
              AND (p.seller_id IS NULL OR (s.status = 'APPROVED' AND s.review_state = 'CLEAR' AND s.maintenance_mode = 0))
            """,
            (product_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return serialize_product(row)
