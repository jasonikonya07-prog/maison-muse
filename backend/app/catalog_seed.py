import json
import re
import sqlite3
from pathlib import Path


PRODUCTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "data"
    / "products.json"
)

LEGACY_PRODUCT_IDS = (
    "rose-oud-eau-de-parfum",
    "vanilla-silk-fragrance-mist",
    "citrus-bloom-perfume-oil",
    "rosewater-glow-nail-set",
    "cherry-glaze-press-on-set",
    "pearl-french-nail-set",
    "cloud-nine-barrier-cream",
    "dew-drop-vitamin-c-serum",
    "petal-soft-cleansing-balm",
    "everyday-gold-hoops",
    "blush-velvet-cosmetic-pouch",
    "silk-scrunchie-trio",
)
AGRI_IMAGE_BASE = "https://images.unsplash.com/{photo}?q=80&w=800"
AGRI_FARM_PRODUCTS = [
    {
        "id": "agri-nilzan-super-dewormer",
        "name": "Nilzan Super Livestock Dewormer (Dawa ya Minyoo - 1 Litre)",
        "brand": "Nilzan",
        "sku": "AGRI-NILZAN-1L",
        "category": "Veterinary Medicines",
        "detail": "One-litre livestock dewormer for cattle and sheep.",
        "description": "Nilzan Super livestock dewormer, 1 litre. Follow the product label and consult a veterinary professional for animal-specific guidance.",
        "price": 2800,
        "stock": 24,
        "photo": "photo-1584308666744-24d5c474f2ae",
        "farmer_name": "Rift Valley Vet Supplies",
        "features": ["1 litre bottle", "Livestock treatment", "Use according to label directions"],
    },
    {
        "id": "agri-bimectin-ivermectin",
        "name": "Bimectin Ivermectin Injection (Broad-Spectrum Dewormer & Tick Control)",
        "brand": "Bimectin",
        "sku": "AGRI-BIMECTIN-INJ",
        "category": "Veterinary Medicines",
        "detail": "Ivermectin livestock injection for veterinary use.",
        "description": "Bimectin ivermectin injection for livestock. Use only under the direction of a qualified veterinary professional and follow label and withdrawal-period guidance.",
        "price": 1950,
        "stock": 18,
        "photo": "photo-1576602976047-174e57a47881",
        "farmer_name": "Rift Valley Vet Supplies",
        "features": ["Broad-spectrum livestock treatment", "Veterinary use", "Professional guidance required"],
    },
    {
        "id": "agri-friesian-in-calf-heifer",
        "name": "Pedigree Friesian In-Calf Heifer (5 Months Pregnant)",
        "brand": "Green Valley Farm",
        "sku": "AGRI-FRIESIAN-HEIFER",
        "category": "Dairy Cattle",
        "detail": "Pedigree Friesian heifer, reported five months in calf.",
        "description": "Pedigree Friesian in-calf heifer offered by a local farm. Buyers should arrange an in-person inspection and verify veterinary and breeding records before purchase.",
        "price": 185000,
        "stock": 1,
        "photo": "/farm-cattle.svg",
        "farmer_name": "Green Valley Farm",
        "features": ["Friesian dairy breed", "Reported five months in calf", "Inspect and verify records with the farmer"],
    },
    {
        "id": "agri-fleckvieh-dairy-cow",
        "name": "Purebred Fleckvieh High-Yield Dairy Cow (30L/Day)",
        "brand": "Highland Dairy Farm",
        "sku": "AGRI-FLECKVIEH-COW",
        "category": "Dairy Cattle",
        "detail": "Fleckvieh dairy cow with seller-reported 30 litre daily yield.",
        "description": "Purebred Fleckvieh dairy cow with seller-reported yield of up to 30 litres per day. Arrange inspection and independently verify production and veterinary records.",
        "price": 220000,
        "stock": 1,
        "photo": "/farm-cattle.svg",
        "farmer_name": "Highland Dairy Farm",
        "features": ["Fleckvieh breed", "Seller-reported 30 litres/day", "Inspect and verify production records"],
    },
    {
        "id": "agri-boer-breeding-buck",
        "name": "Boer Breeding Buck (High-Genetics Male Goat)",
        "brand": "Rift Valley Goat Farm",
        "sku": "AGRI-BOER-BUCK",
        "category": "Goats & Sheep",
        "detail": "Boer breeding buck offered by a local livestock farmer.",
        "description": "Boer breeding buck marketed for its genetics. Arrange an in-person inspection and verify animal health and breeding records directly with the farmer.",
        "price": 45000,
        "stock": 1,
        "photo": "photo-1524024973431-2ad916746881",
        "farmer_name": "Rift Valley Goat Farm",
        "features": ["Boer goat", "Breeding stock", "Inspect and verify health records"],
    },
    {
        "id": "agri-kienyeji-cockerels-pair",
        "name": "Improved Kienyeji Mature Cockerels (Pair)",
        "brand": "Sunrise Poultry Farm",
        "sku": "AGRI-KIENYEJI-PAIR",
        "category": "Poultry & Fowl",
        "detail": "Pair of mature improved Kienyeji cockerels.",
        "description": "Pair of mature improved Kienyeji cockerels from a local poultry farm. Confirm availability, collection arrangements, and animal health details with the farmer.",
        "price": 3200,
        "stock": 10,
        "photo": "photo-1548550023-2bdb3c5beed7",
        "farmer_name": "Sunrise Poultry Farm",
        "features": ["Pair of mature cockerels", "Improved Kienyeji type", "Confirm collection details with the farmer"],
    },
    {
        "id": "agri-white-broilers-pack-five",
        "name": "Fattened White Broiler Chickens (Pack of 5)",
        "brand": "Sunrise Poultry Farm",
        "sku": "AGRI-WHITE-BROILERS-5",
        "category": "Poultry & Fowl",
        "detail": "Pack of five fattened white broiler chickens.",
        "description": "Pack of five fattened white broiler chickens from a local poultry farm. Contact the farmer to confirm live-bird or processed availability and collection arrangements.",
        "price": 3500,
        "stock": 8,
        "photo": "photo-1516467508483-a7212febe31a",
        "farmer_name": "Sunrise Poultry Farm",
        "features": ["Pack of five", "White broiler chickens", "Confirm product form and collection with the farmer"],
    },
]
AGRI_WHATSAPP_NUMBER = "+254712345678"


def load_products() -> list[dict]:
    with PRODUCTS_PATH.open(encoding="utf-8") as catalog_file:
        products = json.load(catalog_file)
    if not isinstance(products, list):
        raise ValueError(f"Product catalog at {PRODUCTS_PATH} must be a JSON array.")
    return products


def seed_products(connection: sqlite3.Connection) -> None:
    products = load_products()
    connection.executemany(
        """
        INSERT OR IGNORE INTO products (
            id, name, brand, sku, category, detail, price, old_price, discount,
            rating, reviews_count, tag, tag_color, description, stock, image,
            gallery_json, notes_json, nail_sizes_json, highlights_json,
            details_json, tone, active, low_stock_threshold
        ) VALUES (
            :id, :name, :brand, :sku, :category, :detail, :price, :old_price, :discount,
            :rating, :reviews_count, :tag, :tag_color, :description, :stock, :image,
            :gallery_json, :notes_json, :nail_sizes_json, :highlights_json,
            :details_json, :tone, 1, 5
        )
        """,
        [
            {
                **product,
                "sku": product["id"].upper(),
                "detail": product["description"].split(". ", 1)[0] + ".",
                "old_price": product["oldPrice"],
                "reviews_count": product["reviewsCount"],
                "tag_color": product["tagColor"],
                "stock": 24 if product["inStock"] else 0,
                "image": product["images"][0],
                "gallery_json": json.dumps(product["images"]),
                "notes_json": json.dumps([]),
                "nail_sizes_json": json.dumps(
                    product["details"].get("availableSizes", [])
                ),
                "highlights_json": json.dumps(
                    [
                        f"{key}: {', '.join(value) if isinstance(value, list) else value}"
                        for key, value in product["details"].items()
                        if key != "availableSizes"
                    ]
                ),
                "details_json": json.dumps(product["details"]),
                "tone": (
                    "rose"
                    if "Perfumes" in product["category"] or "Makeup" in product["category"]
                    else "peach"
                    if "Nails" in product["category"]
                    else "cream"
                    if "Skincare" in product["category"]
                    else "lilac"
                ),
            }
            for product in products
        ],
    )
    connection.executemany(
        "UPDATE products SET active = 0 WHERE id = ?",
        [(product_id,) for product_id in LEGACY_PRODUCT_IDS],
    )
    connection.execute(
        """INSERT INTO categories (name, slug, parent_id, icon_name)
           VALUES ('Agriculture & Livestock', 'agriculture-livestock', NULL, 'Sprout')
           ON CONFLICT(slug) DO UPDATE SET
               name = excluded.name, parent_id = NULL, icon_name = excluded.icon_name"""
    )
    agriculture = connection.execute(
        "SELECT id FROM categories WHERE slug = 'agriculture-livestock'"
    ).fetchone()
    for product in AGRI_FARM_PRODUCTS:
        category_slug = re.sub(
            r"-+", "-", re.sub(r"[^a-z0-9]+", "-", product["category"].casefold())
        ).strip("-")
        connection.execute(
            """INSERT INTO categories (name, slug, parent_id, icon_name)
               VALUES (?, ?, ?, 'Sprout')
               ON CONFLICT(slug) DO UPDATE SET
                   name = excluded.name, parent_id = excluded.parent_id""",
            (product["category"], f"agriculture-livestock-{category_slug}", agriculture["id"]),
        )
        image_url = (
            product["photo"]
            if product["photo"].startswith("/")
            else AGRI_IMAGE_BASE.format(photo=product["photo"])
        )
        features_json = json.dumps(product["features"])
        connection.execute(
            """
            INSERT OR IGNORE INTO products (
                id, name, brand, sku, category, detail, description, price,
                old_price, discount, rating, reviews_count, tag, tag_color,
                stock, low_stock_threshold, image, gallery_json, tags_json,
                variants_json, product_status, highlights_json, details_json,
                tone, active, title, slug, category_slug, sub_category,
                features_json, image_url, seller_name, seller_slug, seller_phone,
                seller_whatsapp_phone, seller_verified, is_agri_product,
                farmer_name, farmer_whatsapp
            ) VALUES (
                :id, :name, :brand, :sku, :category, :detail, :description, :price,
                NULL, '', 4.8, 0, 'FARM DIRECT', 'bg-emerald-600',
                :stock, 2, :image, :gallery_json, :tags_json,
                '[]', 'ACTIVE', :features_json, :details_json,
                'cream', 1, :name, :slug, 'agriculture-livestock', :category,
                :features_json, :image, :brand, '', :farmer_whatsapp,
                :farmer_whatsapp, 0, 1, :farmer_name, :farmer_whatsapp
            )
            ON CONFLICT(id) DO UPDATE SET
                image = excluded.image,
                image_url = excluded.image_url,
                gallery_json = excluded.gallery_json
            """,
            {
                **product,
                "image": image_url,
                "gallery_json": json.dumps([image_url]),
                "tags_json": json.dumps(["farm-direct", category_slug]),
                "features_json": features_json,
                "details_json": json.dumps(
                    {
                        "Category": "Agriculture & Livestock",
                        "Listing type": product["category"],
                        "Sales channel": "Direct farmer-to-buyer WhatsApp",
                    }
                ),
                "slug": product["id"],
                "farmer_whatsapp": AGRI_WHATSAPP_NUMBER,
            },
        )
