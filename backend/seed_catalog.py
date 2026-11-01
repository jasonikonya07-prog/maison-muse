import json
import re
from pathlib import Path

from dotenv import load_dotenv

from app.database import get_connection, initialize_database

load_dotenv(Path(__file__).resolve().parent / ".env")


SELLER_NAME = "Luxe Scents Nairobi"
SELLER_SLUG = "luxe-scents-nairobi"
SELLER_PHONE = "0712345678"
IMAGE_BASE = "https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1200&q=85"

CATEGORIES = [
    {
        "name": "Beauty & Cosmetics",
        "slug": "beauty-cosmetics",
        "icon": "Sparkles",
        "products": [
            ("Luxury Velvet Press-On Nails Set", 1800, "Press-On Nails", "photo-1604654894610-df63bc536371", "A salon-finished reusable nail set with a soft velvet sheen and a comfortable, natural fit.", ["Reusable salon-quality finish", "Includes multiple nail sizes", "Adhesive tabs and application guide included"]),
            ("Hydrating Hyaluronic Face Serum 30ml", 3200, "Skincare Serum", "photo-1608248543803-ba4f8c70ae0b", "A lightweight daily serum formulated to leave skin feeling supple and comfortably hydrated.", ["30 ml glass dropper bottle", "Layer-friendly lightweight texture", "Use after cleansing, before moisturizer"]),
        ],
    },
    {
        "name": "Electronics",
        "slug": "electronics",
        "icon": "Laptop",
        "products": [
            ("Samsung Galaxy S24 Ultra 256GB", 145000, "Smartphones", "photo-1511707171634-5f897ff02aa9", "A premium large-screen smartphone with a versatile camera system and generous 256GB storage.", ["256GB internal storage", "Large high-resolution AMOLED display", "Advanced multi-lens camera system"]),
            ("HP ProBook 450 G9 i7 16GB RAM", 88000, "Laptops", "photo-1496181133206-80ce9b88a853", "A business-ready laptop configured for productive multitasking, video meetings, and everyday office work.", ["Intel Core i7 processor", "16GB memory for multitasking", "15.6-inch class productivity display"]),
        ],
    },
    {
        "name": "Fashion & Clothing",
        "slug": "fashion-clothing",
        "icon": "Shirt",
        "products": [
            ("Men's Slim Fit Casual Denim Jeans", 2500, "Men's Clothing", "photo-1542272604-787c3835535d", "Versatile slim-fit denim with a clean wash, comfortable stretch, and an easy everyday silhouette.", ["Slim-fit cut", "Comfort-stretch denim", "Classic five-pocket design"]),
            ("Women's Floral Summer Maxi Dress", 3200, "Women's Clothing", "photo-1496747611176-843222e1e57c", "A light, flowing maxi dress finished with a delicate floral print for warm days and relaxed occasions.", ["Breathable lightweight fabric", "Full-length flowing silhouette", "Floral print for day-to-evening wear"]),
        ],
    },
    {
        "name": "Home & Furniture",
        "slug": "home-furniture",
        "icon": "Armchair",
        "products": [
            ("5-Seater Modern Velvet L-Shape Sofa", 65000, "Living Room Furniture", "photo-1555041469-a586c61ea9bc", "A generously proportioned velvet-look sectional designed to anchor a modern living room.", ["Five-seat L-shaped configuration", "Soft-touch upholstery", "Contemporary low-profile design"]),
            ("Solid Wood Executive Office Desk", 28000, "Office Furniture", "photo-1497366754035-f200968a6e72", "A substantial solid-wood workspace with a generous top for focused work and a polished office presence.", ["Solid wood construction", "Wide work surface", "Suitable for a home or executive office"]),
        ],
    },
    {
        "name": "Groceries & Food",
        "slug": "groceries-food",
        "icon": "ShoppingBasket",
        "products": [
            ("Premium Fortified Maize Flour 2kg (Pack of 6)", 1100, "Pantry Staples", "photo-1574323347407-f5e1ad6d020b", "A value pack of six 2kg bags of fortified maize flour for everyday family meals.", ["Six sealed 2kg packs", "Fortified household staple", "Store in a cool, dry place"]),
            ("Pure Golden Vegetable Cooking Oil 3L", 950, "Cooking Oils", "photo-1474979266404-7eaacbcd87c5", "A versatile golden cooking oil in a family-size 3-litre bottle for frying, baking, and everyday cooking.", ["3-litre bottle", "Neutral everyday cooking profile", "Secure, easy-pour cap"]),
        ],
    },
    {
        "name": "Phones & Accessories",
        "slug": "phones-accessories",
        "icon": "Smartphone",
        "products": [
            ("Anker 65W Fast Charging USB-C Adapter", 4500, "Chargers & Adapters", "photo-1583394838336-acd977736f90", "A compact USB-C power adapter for fast, convenient charging of compatible phones, tablets, and laptops.", ["Up to 65W USB-C output", "Compact travel-friendly form", "Compatible USB-C cable sold separately"]),
            ("Magnetic Wireless Power Bank 10000mAh", 3800, "Power Banks", "photo-1609091839311-d5365f9ff1c5", "A pocketable 10,000mAh power bank with magnetic wireless charging for compatible devices.", ["10,000mAh capacity", "Magnetic wireless charging support", "USB output for wired charging"]),
        ],
    },
    {
        "name": "Baby & Kids",
        "slug": "baby-kids",
        "icon": "Baby",
        "products": [
            ("Ergonomic 4-in-1 Baby Carrier Sling", 3500, "Baby Carriers", "photo-1519689680058-324335c77eba", "A supportive multi-position carrier designed to keep everyday outings close, hands-free, and comfortable.", ["Four carrying positions", "Adjustable shoulder and waist straps", "Follow included age and weight guidance"]),
            ("Interactive Wooden Building Blocks Set", 2200, "Learning Toys", "photo-1599623560574-39d485900c95", "A colorful wooden block set that invites young builders to explore shapes, balance, and imaginative play.", ["Smooth-finished wooden pieces", "Encourages creative, hands-on play", "Adult supervision recommended"]),
        ],
    },
    {
        "name": "Sports & Outdoors",
        "slug": "sports-outdoors",
        "icon": "Dumbbell",
        "products": [
            ("High-Density Non-Slip Yoga Mat 10mm", 2400, "Fitness Accessories", "photo-1592432678016-e910b452f9a2", "A cushioned exercise mat with a textured surface for stable home workouts and restorative stretching.", ["10mm supportive cushioning", "Textured non-slip surface", "Easy to roll and store"]),
            ("Professional Adjustable Dumbbell Set 20kg", 12500, "Strength Training", "photo-1583454110551-21f2fa2afe61", "An adjustable dumbbell set for progressive strength sessions in a compact home-training space.", ["Up to 20kg total set weight", "Adjustable resistance configuration", "Use on a stable, clear workout surface"]),
        ],
    },
    {
        "name": "Automotive",
        "slug": "automotive",
        "icon": "Car",
        "products": [
            ("Ultra-Bright LED Headlight Conversion Kit", 5500, "Car Lighting", "photo-1486262715619-67b85e0b08d3", "A matched LED conversion kit for drivers seeking a crisp, modern headlight appearance.", ["Pair kit for compatible vehicles", "Check fitment before purchase", "Professional installation recommended"]),
            ("Heavy-Duty Full Car Floor Mats Set", 4200, "Interior Accessories", "photo-1503376780353-7e6692767b70", "A durable full-set floor mat collection designed to help protect a vehicle's cabin from daily dirt and spills.", ["Full interior mat set", "Easy-clean heavy-duty surface", "Trim and fit to vehicle where required"]),
        ],
    },
    {
        "name": "Agriculture & Garden",
        "slug": "agriculture-garden",
        "icon": "Sprout",
        "products": [
            ("Automatic 360-Degree Garden Lawn Sprinkler", 1800, "Garden Irrigation", "photo-1416879595882-3373a0480b5b", "A rotating lawn sprinkler that distributes water across a broad area for everyday garden care.", ["360-degree rotating spray", "Connects to a standard garden hose", "Coverage depends on water pressure"]),
            ("High-Pressure Extendable Garden Hose 30m", 3600, "Garden Tools", "photo-1558618666-fcd25c85cd64", "A flexible 30-metre hose for watering, rinsing, and routine outdoor cleanup around the home.", ["30-metre extended length", "Flexible, space-saving storage", "Use with compatible hose fittings"]),
        ],
    },
    {
        "name": "Computers & Accessories",
        "slug": "computers-accessories",
        "icon": "Keyboard",
        "products": [
            ("Mechanical RGB Gaming Keyboard (Red Switches)", 6500, "Keyboards", "photo-1587829741301-dc798b83add3", "A responsive mechanical keyboard with red switches and customizable RGB lighting for gaming or desktop work.", ["Linear red mechanical switches", "RGB backlighting", "USB wired connection"]),
            ("Ultra-Wide 27-Inch 4K IPS Monitor", 34000, "Monitors", "photo-1527443224154-c4a3942d3acf", "A 27-inch 4K IPS display built for detailed creative work, clear documents, and immersive entertainment.", ["27-inch 4K resolution", "IPS panel viewing angles", "Confirm available ports before purchase"]),
        ],
    },
    {
        "name": "Health & Personal Care",
        "slug": "health-personal-care",
        "icon": "HeartPulse",
        "products": [
            ("Professional Cordless Hair Clipper Kit", 3800, "Grooming Tools", "photo-1621605815971-fbc98d665033", "A cordless clipper kit with interchangeable guards for convenient at-home grooming and touch-ups.", ["Rechargeable cordless operation", "Guide combs included", "Clean and oil blades after use"]),
            ("Deep Tissue Percussion Massage Gun", 7500, "Recovery & Wellness", "photo-1518611012118-696072aa579a", "A handheld percussion massager with multiple speed settings for post-workout relaxation and recovery routines.", ["Multiple percussion speed levels", "Interchangeable massage heads", "Not a substitute for medical care"]),
        ],
    },
    {
        "name": "Books & Stationery",
        "slug": "books-stationery",
        "icon": "BookOpen",
        "products": [
            ("Scientific Financial & Engineering Calculator", 2800, "Calculators", "photo-1587145820266-a5951ee6f620", "A multi-function scientific calculator for finance, engineering, and advanced classroom calculations.", ["Scientific and financial functions", "Multi-line calculation display", "Includes protective cover"]),
            ("Ergonomic Multi-Pocket School Backpack", 2400, "School Supplies", "photo-1553062407-98eeb64c6a62", "A practical, ergonomic backpack with organized pockets for school books, stationery, and daily essentials.", ["Padded adjustable shoulder straps", "Multiple storage compartments", "Wipe-clean durable outer fabric"]),
        ],
    },
    {
        "name": "Kitchen & Dining",
        "slug": "kitchen-dining",
        "icon": "CookingPot",
        "products": [
            ("Digital Touchscreen Air Fryer 5.5L", 14500, "Small Appliances", "photo-1585515320310-259814833e62", "A spacious digital air fryer with touchscreen controls for convenient weeknight cooking.", ["5.5-litre cooking capacity", "Digital touchscreen controls", "Follow the included cleaning and safety guide"]),
            ("Heavy-Duty Stainless Steel Electric Kettle 2L", 2200, "Kettles & Tea", "photo-1544787219-7f47ccb76574", "A 2-litre stainless steel electric kettle for quick tea, coffee, and everyday hot-water needs.", ["2-litre capacity", "Stainless steel body", "Automatic shut-off function"]),
        ],
    },
    {
        "name": "Travel & Luggage",
        "slug": "travel-luggage",
        "icon": "Luggage",
        "products": [
            ("360-Spinner Hardshell Travel Suitcase 24-Inch", 9500, "Suitcases", "photo-1565026057447-bc90a3dceb87", "A protective 24-inch hardshell suitcase with smooth spinner wheels for organized trips and longer weekends.", ["24-inch checked-luggage size", "360-degree spinner wheels", "Interior compression straps"]),
            ("Waterproof Travel Duffel Bag with Shoe Pocket", 3400, "Travel Bags", "photo-1553062407-98eeb64c6a62", "A versatile travel duffel with a separate shoe pocket and water-resistant finish for gym sessions and getaways.", ["Dedicated shoe compartment", "Water-resistant outer finish", "Adjustable shoulder strap"]),
        ],
    },
    {
        "name": "Lighting & Electrical",
        "slug": "lighting-electrical",
        "icon": "Lightbulb",
        "products": [
            ("Outdoor Waterproof Solar Security Flood Light 100W", 4800, "Outdoor Lighting", "photo-1507473885765-e6ed057f782c", "A solar-powered outdoor floodlight for added illumination around entrances, paths, and garden areas.", ["Solar-powered charging", "Outdoor weather-resistant housing", "Mount in a sun-exposed location"]),
            ("Smart RGB Wi-Fi Ceiling Ambient Lamp", 5200, "Smart Lighting", "photo-1507473885765-e6ed057f782c", "A connected ambient ceiling lamp with configurable RGB lighting for a personalized room atmosphere.", ["RGB ambient light modes", "Wi-Fi smart control", "Check ceiling fitting and app compatibility"]),
        ],
    },
    {
        "name": "Pet Supplies",
        "slug": "pet-supplies",
        "icon": "PawPrint",
        "products": [
            ("Orthopedic Washable Dog Memory Foam Bed", 4500, "Pet Beds", "photo-1541599540903-216a46ca1dc0", "A supportive washable pet bed with a memory-foam-style cushion for a comfortable place to rest.", ["Removable washable cover", "Supportive cushioned base", "Choose size to suit your pet"]),
            ("Automatic Cat & Dog Water Fountain Dispenser", 3200, "Pet Feeding", "photo-1573865526739-10659fec78a5", "A circulating water fountain designed to encourage cats and dogs to drink fresh water throughout the day.", ["Continuous water circulation", "Removable parts for cleaning", "Keep filled and clean regularly"]),
        ],
    },
    {
        "name": "Musical Instruments",
        "slug": "musical-instruments",
        "icon": "Music2",
        "products": [
            ("Full-Size Cutaway Acoustic Guitar Set", 9800, "Guitars", "photo-1510915361894-db8b60106cb1", "A full-size cutaway acoustic guitar bundle for practice, lessons, and relaxed unplugged sessions.", ["Full-size cutaway body", "Starter accessory set included", "Setup may be adjusted to playing preference"]),
            ("61-Key Touch Sensitive Electronic Keyboard", 18500, "Keyboards & Pianos", "photo-1520523839897-bd0b52f945a0", "A versatile 61-key electronic keyboard with touch response for expressive practice and home performance.", ["61 touch-sensitive keys", "Multiple instrument voices", "Power adapter and stand sold separately unless noted"]),
        ],
    },
]


def _slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.casefold())).strip("-")


def seed_catalog() -> dict[str, int]:
    initialize_database()
    product_count = 0
    category_count = 0
    with get_connection() as connection:
        for category in CATEGORIES:
            connection.execute(
                """
                INSERT INTO categories (name, slug, parent_id, icon_name)
                VALUES (?, ?, NULL, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name = excluded.name, icon_name = excluded.icon_name
                """,
                (category["name"], category["slug"], category["icon"]),
            )
            root = connection.execute(
                "SELECT id FROM categories WHERE slug = ?", (category["slug"],)
            ).fetchone()
            category_count += 1

            for title, price, subcategory, photo_id, description, features in category["products"]:
                subcategory_slug = f"{category['slug']}-{_slugify(subcategory)}"
                connection.execute(
                    """
                    INSERT INTO categories (name, slug, parent_id, icon_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(slug) DO UPDATE SET
                        name = excluded.name, parent_id = excluded.parent_id
                    """,
                    (subcategory, subcategory_slug, root["id"], category["icon"]),
                )
                image_url = IMAGE_BASE.format(photo=photo_id)
                product_slug = _slugify(title)
                product_id = f"catalog-{product_slug}"
                feature_json = json.dumps(features, ensure_ascii=False)
                detail = features[0]
                connection.execute(
                    """
                    INSERT INTO products (
                        id, name, brand, sku, category, detail, price, old_price,
                        discount, rating, reviews_count, tag, tag_color,
                        description, stock, low_stock_threshold, image,
                        gallery_json, tags_json, variants_json, product_status,
                        highlights_json, details_json, tone, active,
                        title, slug, category_slug, sub_category, features_json,
                        image_url, seller_name, seller_slug, seller_phone,
                        seller_verified
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL, '', 4.8, 24,
                            'VERIFIED PICK', 'bg-amber-500', ?, 20, 5, ?,
                            ?, ?, '[]', 'ACTIVE', ?, ?, 'rose', 1,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name, brand = excluded.brand,
                        sku = excluded.sku, category = excluded.category,
                        detail = excluded.detail, price = excluded.price,
                        description = excluded.description,
                        stock = excluded.stock, image = excluded.image,
                        gallery_json = excluded.gallery_json,
                        tags_json = excluded.tags_json,
                        highlights_json = excluded.highlights_json,
                        details_json = excluded.details_json,
                        title = excluded.title, slug = excluded.slug,
                        category_slug = excluded.category_slug,
                        sub_category = excluded.sub_category,
                        features_json = excluded.features_json,
                        image_url = excluded.image_url,
                        seller_name = excluded.seller_name,
                        seller_slug = excluded.seller_slug,
                        seller_phone = excluded.seller_phone,
                        seller_verified = excluded.seller_verified,
                        active = 1, product_status = 'ACTIVE'
                    """,
                    (
                        product_id,
                        title,
                        "Maison Muse Curated",
                        f"MM-{product_slug[:48].upper()}",
                        category["name"],
                        detail,
                        price,
                        description,
                        image_url,
                        json.dumps([image_url]),
                        json.dumps(["verified", _slugify(subcategory)]),
                        feature_json,
                        json.dumps(
                            {
                                "Category": category["name"],
                                "Specialty": subcategory,
                                "Seller": SELLER_NAME,
                            }
                        ),
                        title,
                        product_slug,
                        category["slug"],
                        subcategory,
                        feature_json,
                        image_url,
                        SELLER_NAME,
                        SELLER_SLUG,
                        SELLER_PHONE,
                    ),
                )
                product_count += 1
        connection.commit()

    if category_count != 18 or product_count != 36:
        raise RuntimeError(
            f"Catalog seed definition must contain 18 root categories and 36 products; found {category_count} and {product_count}."
        )
    return {"root_categories": category_count, "products_seeded": product_count}


if __name__ == "__main__":
    counts = seed_catalog()
    print(
        f"Seeded {counts['products_seeded']} catalog products across "
        f"{counts['root_categories']} root categories in the configured SQLite database."
    )
