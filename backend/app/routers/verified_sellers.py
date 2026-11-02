from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.routers.products import serialize_product


router = APIRouter()

CATEGORY_FILTERS = {
    "perfumeries": "Perfumes & Fragrances",
    "nail studios": "Press-On Nails",
    "skincare labs": "Skincare & Glow",
    "makeup brands": "Lip & Makeup Essentials",
}


@router.get("/verified")
def list_verified_sellers(
    search: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=60),
    sort: str = Query(default="popularity", pattern="^(popularity|rating)$"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    conditions = [
        "s.status = 'APPROVED'",
        "s.review_state = 'CLEAR'",
        "s.maintenance_mode = 0",
    ]
    parameters: list[object] = []
    normalized_search = search.strip()
    normalized_category = category.strip()
    if normalized_search:
        search_pattern = f"%{normalized_search}%"
        conditions.append(
            "(s.store_name LIKE ? COLLATE NOCASE OR s.city LIKE ? COLLATE NOCASE "
            "OR s.business_category LIKE ? COLLATE NOCASE)"
        )
        parameters.extend([search_pattern, search_pattern, search_pattern])
    if normalized_category and normalized_category.casefold() != "all sellers":
        matching_category = CATEGORY_FILTERS.get(
            normalized_category.casefold(), normalized_category
        )
        conditions.append("s.business_category = ? COLLATE NOCASE")
        parameters.append(matching_category)

    where_clause = " AND ".join(conditions)
    order_clause = (
        "s.rating DESC, sales_count DESC, s.store_name COLLATE NOCASE"
        if sort == "rating"
        else "sales_count DESC, s.rating DESC, s.store_name COLLATE NOCASE"
    )
    with get_connection() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM sellers s WHERE {where_clause}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT s.id, s.store_name, s.store_slug, s.logo_url, s.banner_url,
                   s.business_category, s.city, s.rating,
                   s.business_phone, s.whatsapp_phone,
                   COUNT(DISTINCT CASE WHEN o.payment_status IN ('paid', 'completed_demo') THEN o.id END)
                       AS sales_count,
                   COUNT(DISTINCT CASE WHEN p.active = 1 AND p.product_status = 'ACTIVE' THEN p.id END)
                       AS total_listings
            FROM sellers s
            LEFT JOIN sub_orders so ON so.seller_id = s.id
            LEFT JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN products p ON p.seller_id = s.id
            WHERE {where_clause}
            GROUP BY s.id
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
            """,
            [*parameters, limit, offset],
        ).fetchall()
        seller_ids = [row["id"] for row in rows]
        product_samples: dict[int, list[dict[str, str]]] = {
            seller_id: [] for seller_id in seller_ids
        }
        if seller_ids:
            placeholders = ",".join("?" for _ in seller_ids)
            products = connection.execute(
                f"""
                SELECT seller_id, name, image
                FROM (
                    SELECT seller_id, name, image,
                           ROW_NUMBER() OVER (
                               PARTITION BY seller_id ORDER BY name COLLATE NOCASE
                           ) AS sample_rank
                    FROM products
                    WHERE active = 1 AND product_status = 'ACTIVE'
                      AND seller_id IN ({placeholders})
                )
                WHERE sample_rank <= 3
                """,
                seller_ids,
            ).fetchall()
            for product in products:
                product_samples[product["seller_id"]].append(
                    {"name": product["name"], "image": product["image"]}
                )

    items = [
        {
            "id": row["id"],
            "store_name": row["store_name"],
            "store_slug": row["store_slug"],
            "logo_url": row["logo_url"],
            "banner_url": row["banner_url"],
            "category": row["business_category"],
            "city": row["city"],
            "rating": row["rating"],
            "sales_count": row["sales_count"],
            "total_listings": row["total_listings"],
            "product_samples": product_samples[row["id"]],
            "business_phone": row["business_phone"],
            "seller_phone": row["business_phone"],
            "seller_verified": True,
            "whatsapp_phone": row["whatsapp_phone"] or row["business_phone"],
        }
        for row in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/inspect")
def inspect_seller(query: str = Query(min_length=1, max_length=120)) -> dict:
    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(status_code=422, detail="Enter a seller name or ID.")
    with get_connection() as connection:
        seller = connection.execute(
            """
            SELECT s.id, s.user_id, COALESCE(sp.store_name, s.store_name) AS store_name,
                   s.store_slug, COALESCE(sp.business_category, s.business_category)
                       AS business_category,
                   s.business_type, COALESCE(sp.business_phone, s.business_phone)
                       AS business_phone,
                   s.whatsapp_phone, s.whatsapp_number, s.city, s.status,
                   s.review_state, s.rating, s.created_at, u.phone AS account_phone
            FROM sellers s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN seller_profiles sp ON sp.seller_id = s.id
            WHERE CAST(s.id AS TEXT) = ?
               OR s.store_name = ? COLLATE NOCASE
               OR s.store_slug = ? COLLATE NOCASE
               OR s.store_name LIKE ? COLLATE NOCASE
            ORDER BY CASE
                WHEN s.store_name = ? COLLATE NOCASE THEN 0
                WHEN s.store_slug = ? COLLATE NOCASE THEN 1
                ELSE 2
            END, s.id
            LIMIT 1
            """,
            (
                normalized_query,
                normalized_query,
                normalized_query,
                f"%{normalized_query}%",
                normalized_query,
                normalized_query,
            ),
        ).fetchone()
        if seller is None:
            raise HTTPException(status_code=404, detail="Seller not found.")
        sales = connection.execute(
            """
            SELECT COUNT(*) AS paid_orders,
                   SUM(CASE WHEN so.fulfillment_status = 'DELIVERED'
                            OR so.admin_override_status = 'DELIVERED'
                       THEN 1 ELSE 0 END) AS delivered_orders
            FROM sub_orders so
            JOIN orders o ON o.id = so.parent_order_id
            WHERE so.seller_id = ?
              AND o.payment_status IN ('paid', 'completed_demo')
            """,
            (seller["id"],),
        ).fetchone()
        disputes = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN md.status = 'OPEN' THEN 1 ELSE 0 END) AS open_count
            FROM marketplace_disputes md
            JOIN sub_orders so ON so.id = md.sub_order_id
            WHERE so.seller_id = ?
            """,
            (seller["id"],),
        ).fetchone()
        review_summary = connection.execute(
            """
            SELECT COUNT(*) AS review_count, AVG(r.rating) AS average_rating
            FROM seller_reviews r
            JOIN sub_orders so ON so.id = r.sub_order_id
            JOIN orders o ON o.id = so.parent_order_id
            WHERE r.seller_id = ? AND r.is_verified = 1
              AND o.payment_status IN ('paid', 'completed_demo')
            """,
            (seller["id"],),
        ).fetchone()
        reviews = connection.execute(
            """
            SELECT r.rating, r.comment, r.created_at, o.order_number,
                   u.full_name AS buyer_name
            FROM seller_reviews r
            JOIN sub_orders so ON so.id = r.sub_order_id
            JOIN orders o ON o.id = so.parent_order_id
            LEFT JOIN users u ON u.id = r.buyer_id
            WHERE r.seller_id = ? AND r.is_verified = 1
              AND o.payment_status IN ('paid', 'completed_demo')
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT 8
            """,
            (seller["id"],),
        ).fetchall()
    paid_orders = sales["paid_orders"] or 0
    delivered_orders = sales["delivered_orders"] or 0
    fulfillment_rate = (
        round(delivered_orders / paid_orders * 100, 1) if paid_orders else 0
    )
    rating = round(
        review_summary["average_rating"]
        if review_summary["average_rating"] is not None
        else seller["rating"] or 0,
        1,
    )
    trust_score = round(
        fulfillment_rate * 0.8 + rating * 20 * 0.2,
        1,
    )
    admin_flags = []
    if seller["status"] == "SUSPENDED":
        admin_flags.append("Suspended by administration")
    elif seller["review_state"] == "UNDER_AUDIT":
        admin_flags.append("Under admin audit")
    if disputes["total"]:
        admin_flags.append(f"{disputes['total']} recorded marketplace dispute(s)")
    if not admin_flags:
        admin_flags.append("No recorded marketplace disputes")
    return {
        "id": seller["id"],
        "store_name": seller["store_name"],
        "store_slug": seller["store_slug"],
        "registered_date": seller["created_at"],
        "is_verified": seller["status"] == "APPROVED"
        and seller["review_state"] == "CLEAR",
        "verification_status": seller["status"],
        "business_type": seller["business_type"] or seller["business_category"],
        "business_category": seller["business_category"],
        "city": seller["city"],
        "phone_number": seller["business_phone"] or seller["account_phone"],
        "whatsapp_number": seller["whatsapp_phone"]
        or seller["whatsapp_number"]
        or seller["business_phone"],
        "admin_flags": admin_flags,
        "trust_score": trust_score,
        "fulfillment_rate": fulfillment_rate,
        "total_sales_count": paid_orders,
        "rating": rating,
        "review_count": review_summary["review_count"],
        "reviews": [
            {
                "rating": review["rating"],
                "comment": review["comment"],
                "created_at": review["created_at"],
                "order_number": review["order_number"],
                "buyer_name": review["buyer_name"] or "Verified buyer",
            }
            for review in reviews
        ],
    }


@router.get("/{store_slug}")
def get_public_seller(store_slug: str) -> dict:
    with get_connection() as connection:
        seller = connection.execute(
            """
            SELECT id, store_name, store_slug, store_bio, business_category,
                   business_phone, whatsapp_phone, logo_url, banner_url,
                   instagram_url, tiktok_url, operating_hours, holiday_mode, rating
            FROM sellers
            WHERE store_slug = ? AND status = 'APPROVED' AND review_state = 'CLEAR'
              AND maintenance_mode = 0
            """,
            (store_slug,),
        ).fetchone()
        if seller is None:
            raise HTTPException(status_code=404, detail="Seller not found.")
        products = connection.execute(
            """
            SELECT p.*, s.store_name AS linked_seller_name,
                   s.store_slug AS linked_seller_slug,
                   s.rating AS seller_rating, s.logo_url AS seller_logo,
                   s.business_phone AS linked_seller_phone,
                   s.whatsapp_phone AS linked_seller_whatsapp_phone,
                   s.whatsapp_number AS linked_farmer_whatsapp_number,
                   s.business_type AS linked_business_type,
                   1 AS seller_verified, s.holiday_mode AS seller_holiday_mode
            FROM products p
            JOIN sellers s ON s.id = p.seller_id
            WHERE p.seller_id = ? AND p.active = 1
              AND p.product_status = 'ACTIVE'
              AND s.status = 'APPROVED' AND s.review_state = 'CLEAR'
            ORDER BY p.name COLLATE NOCASE
            """,
            (seller["id"],),
        ).fetchall()
    public_store = dict(seller)
    public_store["whatsapp_phone"] = (
        public_store["whatsapp_phone"] or public_store["business_phone"]
    )
    public_store["seller_phone"] = public_store["business_phone"]
    public_store["seller_verified"] = True
    return {
        "seller": public_store,
        "products": [serialize_product(product) for product in products],
        "verified": True,
    }
