import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import UPLOAD_ROOT
from app.database import initialize_database
from app.main import create_app
from seed_catalog import seed_catalog


class StoreApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_PATH": str(self.database_path),
                "DATABASE_URL": "",
                "CORS_ORIGINS": "http://localhost:5173",
                "ADMIN_USERNAME": "store-admin",
                "ADMIN_PASSWORD": "test-admin-password",
                "ADMIN_SESSION_SECRET": "test-secret-with-more-than-32-characters",
                "AUTH_JWT_SECRET": "test-auth-signing-secret-with-more-than-32-characters",
                "GOOGLE_CLIENT_ID": "test-google-client.apps.googleusercontent.com",
                "PESAPAL_ENVIRONMENT": "sandbox",
                "PESAPAL_CONSUMER_KEY": "test-consumer-key",
                "PESAPAL_CONSUMER_SECRET": "test-consumer-secret",
                "PESAPAL_CALLBACK_URL": "https://store.example/checkout/pesapal-return",
                "PESAPAL_IPN_URL": "https://api.example/api/payments/pesapal/ipn",
                "PESAPAL_IPN_ID": "test-ipn-id",
                "APP_ENV": "testing",
                "SELLER_DEMO_APPROVAL_ENABLED": "false",
                "SELLER_AUTO_APPROVE_REGISTRATIONS": "false",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temporary_directory.cleanup)
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)
        submit_patch = patch(
            "app.routers.orders.submit_order",
            side_effect=lambda **order: {
                "tracking_id": f"tracking-{order['order_number']}",
                "merchant_reference": order["order_number"],
                "redirect_url": "https://cybqa.pesapal.com/pesapalv3/iframe",
            },
        )
        submit_patch.start()
        self.addCleanup(submit_patch.stop)

    @property
    def admin_write_headers(self) -> dict[str, str]:
        return {
            "Origin": "http://localhost:5173",
            "X-Admin-Request": "1",
        }

    def login_admin(self) -> None:
        response = self.client.post(
            "/api/admin/login",
            json={"username": "store-admin", "password": "test-admin-password"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    @property
    def seller_write_headers(self) -> dict[str, str]:
        return {
            "Origin": "http://localhost:5173",
            "X-Seller-Request": "1",
        }

    def register_seller(self, client: TestClient, store_name: str) -> dict:
        response = client.post(
            "/api/seller/register",
            headers=self.seller_write_headers,
            json={
                "email": f"{store_name.casefold().replace(' ', '')}@example.com",
                "password": "correct-horse-battery",
                "store_name": store_name,
                "owner_name": "Taylor Seller",
                "business_type": "Beauty & Personal Care Cosmetics",
                "business_category": "Beauty & Personal Care Cosmetics",
                "logo_url": "",
                "banner_url": "",
                "business_phone": "+254700000000",
                "payout_method": "M-Pesa",
                "payout_account": "123456",
                "submitted_documents": ["https://docs.example/business-registration.jpg"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def approve_seller(self, seller_id: int) -> None:
        response = self.client.patch(
            f"/api/admin/marketplace/vendors/{seller_id}",
            headers=self.admin_write_headers,
            json={"status": "APPROVED"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def approve_seller_product(self, product_id: str) -> None:
        response = self.client.post(
            f"/api/admin/seller-qc/{product_id}",
            headers=self.admin_write_headers,
            json={"action": "APPROVE", "notes": "Listing quality verified."},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_seeded_products_match_frontend_contract(self) -> None:
        response = self.client.get("/api/products")

        self.assertEqual(response.status_code, 200)
        products = response.json()
        self.assertEqual(len(products), 32)
        marketplace_products = [
            item for item in products if not item["is_agri_product"]
        ]
        farm_products = [item for item in products if item["is_agri_product"]]
        product = marketplace_products[0]
        self.assertTrue(
            {
                "id",
                "name",
                "brand",
                "category",
                "price",
                "oldPrice",
                "discount",
                "reviewsCount",
                "tagColor",
                "image",
                "images",
                "gallery",
                "details",
                "inStock",
                "stock",
                "nailSizes",
                "notes",
                "highlights",
            }.issubset(product)
        )
        self.assertTrue(
            all(
                len(item["images"]) == 2
                and all(
                    image.startswith("https://images.unsplash.com/")
                    for image in item["images"]
                )
                and 1500 <= item["price"] <= 12500
                and item["oldPrice"] > item["price"]
                and item["discount"]
                == f"-{round((item['oldPrice'] - item['price']) / item['oldPrice'] * 100)}%"
                and 4.5 <= item["rating"] <= 5.0
                and 50 <= item["reviewsCount"] <= 600
                and item["inStock"]
                for item in marketplace_products
            )
        )
        self.assertEqual(len({item["id"] for item in products}), 32)
        self.assertEqual(len(farm_products), 7)
        cattle = {
            item["id"]: item["image"]
            for item in farm_products
            if item["id"] in {"agri-friesian-in-calf-heifer", "agri-fleckvieh-dairy-cow"}
        }
        self.assertEqual(
            cattle,
            {
                "agri-friesian-in-calf-heifer": "/farm-cattle.svg",
                "agri-fleckvieh-dairy-cow": "/farm-cattle.svg",
            },
        )
        self.assertTrue(
            all(item["farmer_name"] and item["farmer_whatsapp"] for item in farm_products)
        )
        self.assertEqual(
            {item["price"] for item in farm_products},
            {1950, 2800, 3200, 3500, 45000, 185000, 220000},
        )
        self.assertTrue(
            all(
                (
                    item["image"].startswith("https://images.unsplash.com/")
                    or item["image"] == "/farm-cattle.svg"
                )
                and len(item["images"]) == 1
                for item in farm_products
            )
        )
        self.assertEqual(
            {item["category"] for item in marketplace_products},
            {
                "Perfumes & Fragrances",
                "Press-On Nails",
                "Skincare & Glow",
                "Lip & Makeup Essentials",
                "Hair & Accessories",
            },
        )
        self.assertEqual(
            {item["category"] for item in farm_products},
            {
                "Veterinary Medicines",
                "Dairy Cattle",
                "Goats & Sheep",
                "Poultry & Fowl",
            },
        )

    def test_farm_products_are_direct_contact_only(self) -> None:
        response = self.client.get(
            "/api/products", params={"category": "agriculture-livestock"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        products = response.json()
        self.assertEqual(len(products), 7)
        self.assertTrue(all(item["is_agri_product"] for item in products))
        self.assertTrue(
            all(item["farmer_whatsapp"] == "+254712345678" for item in products)
        )

        checkout_data = {
            "customer": {
                "name": "Casey Buyer",
                "phone": "+254700000002",
                "address": "123 Market Road, Nairobi",
            },
            "items": [{"product_id": products[0]["id"], "quantity": 1}],
        }
        order = self.client.post("/api/orders", json=checkout_data)
        self.assertEqual(order.status_code, 409, order.text)
        self.assertIn("Contact the seller on WhatsApp", order.json()["detail"])

        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            demo_order = self.client.post(
                "/api/orders/checkout",
                json={
                    **checkout_data,
                    "city": "Nairobi",
                    "mpesa_phone": "+254700000002",
                },
            )
        self.assertEqual(demo_order.status_code, 409, demo_order.text)

    def test_product_search_and_category_filters_can_be_combined(self) -> None:
        response = self.client.get(
            "/api/products",
            params={"search": "vanilla", "category": "Perfumes & Fragrances"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], ["perf-04", "perf-03"])

    def test_product_search_matches_brand_and_category_filters_are_exact(self) -> None:
        brand_response = self.client.get("/api/products", params={"search": "Act+Acre"})
        category_response = self.client.get(
            "/api/products", params={"category": "Lip & Makeup Essentials"}
        )

        self.assertEqual([item["id"] for item in brand_response.json()], ["skin-05"])
        self.assertEqual(len(category_response.json()), 4)

    def test_category_and_health_endpoints(self) -> None:
        categories = self.client.get("/api/products/categories")
        health = self.client.get("/api/health")

        self.assertEqual(
            categories.json(),
            [
                "Dairy Cattle",
                "Goats & Sheep",
                "Hair & Accessories",
                "Lip & Makeup Essentials",
                "Perfumes & Fragrances",
                "Poultry & Fowl",
                "Press-On Nails",
                "Skincare & Glow",
                "Veterinary Medicines",
            ],
        )
        self.assertEqual(health.json(), {"status": "ok", "database": "connected"})

    def test_seed_catalog_creates_marketplace_categories_and_exact_product_pairs(self) -> None:
        expected = {"root_categories": 18, "products_seeded": 42}
        self.assertEqual(seed_catalog(), expected)
        self.assertEqual(seed_catalog(), expected)

        categories = self.client.get("/api/categories").json()
        self.assertEqual(len(categories), 19)
        self.assertTrue(
            all(
                category["product_count"] == {
                    "agriculture-livestock": 7,
                    "electronics": 4,
                    "fashion-clothing": 4,
                    "phones-accessories": 4,
                }.get(category["slug"], 2)
                for category in categories
            )
        )
        seeded_consoles = self.client.get(
            "/api/products", params={"search": "PlayStation"}
        ).json()
        self.assertEqual(
            {product["name"] for product in seeded_consoles},
            {
                "PlayStation 5 Slim Disc Edition",
                "PlayStation 4 Slim 1TB Console",
            },
        )
        products = self.client.get("/api/products/category/kitchen-dining").json()
        self.assertEqual(len(products), 2)
        self.assertEqual(
            {product["seller_name"] for product in products}, {"Luxe Scents Nairobi"}
        )
        self.assertEqual(
            {product["seller_phone"] for product in products}, {"0712345678"}
        )
        self.assertTrue(all(product["seller_verified"] for product in products))
        self.assertTrue(all(product["features"] for product in products))

    def test_buyer_auth_registration_login_and_signed_token(self) -> None:
        registration = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Jamie Rivers",
                "email": "jamie@example.com",
                "password": "a-very-secure-password",
                "role": "buyer",
                "phone": "+254700000000",
            },
        )

        self.assertEqual(registration.status_code, 201, registration.text)
        payload = registration.json()
        self.assertEqual(payload["user"]["role"], "buyer")
        self.assertNotIn("password_hash", payload["user"])
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                INSERT INTO seller_login_attempts (email, ip_address, succeeded, created_at)
                VALUES (?, ?, 1, ?)
                """,
                (
                    "jamie@example.com",
                    "127.0.0.1",
                    (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                ),
            )
            connection.commit()
        self.assertEqual(
            self.client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {payload['access_token']}"},
            ).json(),
            payload["user"],
        )
        login = self.client.post(
            "/api/auth/login",
            json={"email": "JAMIE@example.com", "password": "a-very-secure-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["id"], payload["user"]["id"])
        self.login_admin()
        activity = self.client.get("/api/admin/users", headers=self.admin_write_headers)
        self.assertEqual(activity.status_code, 200, activity.text)
        tracked_account = next(
            account for account in activity.json() if account["id"] == payload["user"]["id"]
        )
        self.assertEqual(tracked_account["login_count"], 3)
        self.assertEqual(tracked_account["last_login_provider"], "password")
        invalid_token = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {payload['access_token']}x"},
        )
        self.assertEqual(invalid_token.status_code, 401)
        forbidden_admin = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Admin User",
                "email": "admin@example.com",
                "password": "a-very-secure-password",
                "role": "admin",
                "phone": "+254700000001",
            },
        )
        self.assertEqual(forbidden_admin.status_code, 422)

    def test_buyer_order_history_only_lists_orders_created_for_signed_in_buyer(self) -> None:
        registration = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Order History Buyer",
                "email": "order-history@example.com",
                "password": "a-very-secure-password",
                "role": "buyer",
                "phone": "+254700000022",
            },
        )
        self.assertEqual(registration.status_code, 201, registration.text)
        buyer_headers = {
            "Authorization": f"Bearer {registration.json()['access_token']}"
        }
        no_auth = self.client.get("/api/orders/mine")
        self.assertEqual(no_auth.status_code, 401)

        product = next(
            item
            for item in self.client.get("/api/products").json()
            if not item["is_agri_product"]
        )
        order_response = self.client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "customer": {
                    "name": "Order History Buyer",
                    "phone": "+254700000022",
                    "address": "123 Market Road, Nairobi",
                },
                "items": [{"product_id": product["id"], "quantity": 1}],
            },
        )
        self.assertEqual(order_response.status_code, 201, order_response.text)

        history = self.client.get("/api/orders/mine", headers=buyer_headers)
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)
        self.assertEqual(
            history.json()[0]["order_number"], order_response.json()["order_number"]
        )

        another_buyer = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Different Buyer",
                "email": "different-buyer@example.com",
                "password": "a-very-secure-password",
                "role": "buyer",
                "phone": "+254700000023",
            },
        )
        other_headers = {
            "Authorization": f"Bearer {another_buyer.json()['access_token']}"
        }
        other_history = self.client.get("/api/orders/mine", headers=other_headers)
        self.assertEqual(other_history.status_code, 200, other_history.text)
        self.assertEqual(other_history.json(), [])

    def test_seller_session_can_checkout_as_guest(self) -> None:
        self.register_seller(self.client, "Guest Checkout Seller")
        seller_login = self.client.post(
            "/api/auth/login",
            json={
                "email": "guestcheckoutseller@example.com",
                "password": "correct-horse-battery",
            },
        )
        self.assertEqual(seller_login.status_code, 200, seller_login.text)
        seller_headers = {
            "Authorization": f"Bearer {seller_login.json()['access_token']}"
        }
        product = next(
            item
            for item in self.client.get("/api/products").json()
            if not item["is_agri_product"]
        )
        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            checkout = self.client.post(
                "/api/orders/checkout",
                headers=seller_headers,
                json={
                    "customer": {
                        "name": "Guest Seller Buyer",
                        "phone": "+254700000025",
                        "address": "123 Market Road, Nairobi",
                    },
                    "items": [{"product_id": product["id"], "quantity": 1}],
                    "city": "Nairobi",
                    "mpesa_phone": "0712345678",
                },
            )
        self.assertEqual(checkout.status_code, 201, checkout.text)
        with closing(sqlite3.connect(self.database_path)) as connection:
            buyer_id = connection.execute(
                "SELECT buyer_id FROM orders WHERE order_number = ?",
                (checkout.json()["order_number"],),
            ).fetchone()[0]
        self.assertIsNone(buyer_id)

    def test_seller_registration_requires_terms_and_supported_plan(self) -> None:
        registration = {
            "full_name": "Taylor Seller",
            "email": "taylor-terms@example.com",
            "password": "a-very-secure-password",
            "role": "seller",
            "phone": "+254700000000",
            "store_name": "Taylor Beauty",
            "business_type": "Beauty & Personal Care Cosmetics",
            "city": "Nairobi",
            "payout_number": "254700000000",
            "national_id": "PVT-2026-0042",
        }
        missing_acceptance = self.client.post(
            "/api/auth/register", json=registration
        )
        self.assertEqual(missing_acceptance.status_code, 422)

        invalid_plan = self.client.post(
            "/api/auth/register",
            json={
                **registration,
                "email": "taylor-plan@example.com",
                "accepted_terms": True,
                "selected_plan": "free",
            },
        )
        self.assertEqual(invalid_plan.status_code, 422)

    def test_agriculture_seller_registration_requires_and_persists_whatsapp(self) -> None:
        registration = {
            "full_name": "Jordan Farmer",
            "email": "jordan-farmer@example.com",
            "password": "a-very-secure-password",
            "role": "seller",
            "phone": "+254700000003",
            "store_name": "Green Valley Farm",
            "store_category": "Dairy Cattle",
            "business_type": "Agriculture & Livestock Farming",
            "city": "Nakuru",
            "payout_number": "254700000003",
            "national_id": "FARM-2026-0042",
            "accepted_terms": True,
            "selected_plan": "boutique",
        }

        missing_whatsapp = self.client.post("/api/auth/register", json=registration)
        self.assertEqual(missing_whatsapp.status_code, 422)
        self.assertIn("WhatsApp Business phone number", missing_whatsapp.text)

        registered = self.client.post(
            "/api/auth/register",
            json={**registration, "whatsapp_number": "+254711111111"},
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(
            registered.json()["user"]["business_type"],
            "Agriculture & Livestock Farming",
        )
        self.assertEqual(
            registered.json()["user"]["seller"]["whatsapp_number"],
            "+254711111111",
        )

    def test_seller_auth_creates_profile_and_authorizes_seller_portal(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Taylor Seller",
                "email": "taylor@example.com",
                "password": "a-very-secure-password",
                "role": "seller",
                "phone": "+254700000000",
                "store_name": "Taylor Beauty",
                "store_category": "Skincare & Glow",
                "business_type": "Beauty & Personal Care Cosmetics",
                "city": "Nairobi",
                "payout_number": "254700000000",
                "national_id": "PVT-2026-0042",
                "accepted_terms": True,
                "selected_plan": "pro",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["token"], payload["access_token"])
        self.assertEqual(payload["user"]["seller"]["status"], "PENDING")
        self.assertTrue(payload["user"]["seller"]["accepted_terms"])
        self.assertEqual(payload["user"]["seller"]["selected_plan"], "pro")
        self.assertEqual(payload["user"]["seller"]["commission_rate"], 5)
        token_headers = {"Authorization": f"Bearer {payload['access_token']}"}
        seller_profile = self.client.get("/api/seller/me", headers=token_headers)
        self.assertEqual(seller_profile.status_code, 200, seller_profile.text)
        self.assertEqual(seller_profile.json()["store_name"], "Taylor Beauty")
        self.assertTrue(seller_profile.json()["accepted_terms"])
        self.assertEqual(seller_profile.json()["selected_plan"], "pro")
        self.assertEqual(seller_profile.json()["commission_rate"], 5)

        self.login_admin()
        self.approve_seller(payload["user"]["seller"]["id"])
        marketplace = self.client.get("/api/admin/marketplace").json()
        vendor = next(
            item
            for item in marketplace["vendors"]
            if item["id"] == payload["user"]["seller"]["id"]
        )
        self.assertEqual(vendor["business_category"], "Skincare & Glow")
        self.assertEqual(
            vendor["business_registration_number"], "PVT-2026-0042"
        )
        product = self.client.post(
            "/api/seller/products",
            headers={**self.seller_write_headers, **token_headers},
            json={
                "name": "Taylor Beauty Oil",
                "brand": "Taylor Beauty",
                "sku": "TB-OIL-01",
                "category": "Skincare & Glow",
                "detail": "A gentle daily oil",
                "description": "A gentle daily oil for a soft and hydrated feel.",
                "price": 1800,
                "stock": 5,
                "images": ["https://images.example/taylor-oil.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.assertEqual(product.json()["status"], "DRAFT")
        self.assertEqual(product.json()["qc_status"], "PENDING_QC")
        self.approve_seller_product(product.json()["id"])
        boutiques = self.client.get(
            "/api/sellers/verified?search=nairobi&category=Skincare%20Labs"
        )
        self.assertEqual(boutiques.status_code, 200, boutiques.text)
        directory = boutiques.json()
        self.assertEqual(directory["total"], 1)
        self.assertEqual(directory["items"][0]["store_slug"], "taylor-beauty")
        self.assertEqual(directory["items"][0]["city"], "Nairobi")
        self.assertEqual(directory["items"][0]["total_listings"], 1)
        self.assertEqual(
            directory["items"][0]["product_samples"][0]["name"],
            "Taylor Beauty Oil",
        )

        buyer = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Casey Buyer",
                "email": "casey@example.com",
                "password": "another-secure-password",
                "role": "buyer",
                "phone": "+254700000002",
            },
        ).json()
        buyer_access = self.client.get(
            "/api/seller/me",
            headers={"Authorization": f"Bearer {buyer['access_token']}"},
        )
        self.assertEqual(buyer_access.status_code, 403)

    def test_google_sign_in_verifies_identity_and_creates_buyer_only(self) -> None:
        verified_identity = {
            "aud": "test-google-client.apps.googleusercontent.com",
            "email": "google-buyer@example.com",
            "email_verified": "true",
            "exp": "4102444800",
            "iss": "https://accounts.google.com",
            "name": "Google Buyer",
            "sub": "google-subject-123",
        }
        with patch("app.routers.auth.httpx.get") as google_request:
            google_request.return_value = Mock(status_code=200)
            google_request.return_value.json.return_value = verified_identity
            response = self.client.post(
                "/api/auth/google", json={"credential": "verified-google-id-token"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["user"]["role"], "buyer")
        self.assertEqual(payload["user"]["email"], "google-buyer@example.com")

        unverified_identity = {**verified_identity, "email_verified": "false"}
        with patch("app.routers.auth.httpx.get") as google_request:
            google_request.return_value = Mock(status_code=200)
            google_request.return_value.json.return_value = unverified_identity
            rejected = self.client.post(
                "/api/auth/google", json={"credential": "another-google-id-token"}
            )
        self.assertEqual(rejected.status_code, 401)

    def test_google_simulation_is_fixed_account_and_development_only(self) -> None:
        simulated = self.client.post("/api/auth/google", json={"simulation": True})
        self.assertEqual(simulated.status_code, 200, simulated.text)
        payload = simulated.json()
        self.assertEqual(payload["provider"], "google")
        self.assertEqual(payload["user"]["email"], "jasonikonya1@gmail.com")
        self.assertEqual(payload["user"]["role"], "buyer")
        self.assertTrue(payload["access_token"])

        repeated = self.client.post("/api/auth/google", json={"simulation": True})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["user"]["id"], payload["user"]["id"])

        arbitrary_identity = self.client.post(
            "/api/auth/google",
            json={"simulation": True, "email": "someone-else@example.com"},
        )
        self.assertEqual(arbitrary_identity.status_code, 422)

        with patch.dict(os.environ, {"APP_ENV": "production"}):
            production_simulation = self.client.post(
                "/api/auth/google", json={"simulation": True}
            )
        self.assertEqual(production_simulation.status_code, 403)

    def test_seller_onboarding_rbac_and_private_inventory(self) -> None:
        seller = self.register_seller(self.client, "Velvet Atelier")
        self.assertEqual(seller["status"], "PENDING")
        self.assertEqual(seller["owner_name"], "Taylor Seller")
        self.assertEqual(self.client.get("/api/seller/me").json()["id"], seller["id"])
        rejected_product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Pending Product",
                "brand": "Velvet Atelier",
                "sku": "VA-PENDING",
                "category": "Perfumes & Fragrances",
                "detail": "A product waiting for approval",
                "description": "A carefully blended fragrance awaiting store approval.",
                "price": 1800,
                "stock": 8,
                "images": ["https://images.example/rose.jpg"],
            },
        )
        self.assertEqual(rejected_product.status_code, 403)

        self.login_admin()
        self.approve_seller(seller["id"])
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Velvet Rose Oil",
                "brand": "Velvet Atelier",
                "sku": "VA-ROSE-01",
                "category": "Perfumes & Fragrances",
                "detail": "A soft rose fragrance",
                "description": "A carefully blended rose fragrance for everyday wear.",
                "price": 1800,
                "stock": 8,
                "lowStockThreshold": 2,
                "images": ["https://images.example/rose.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.assertEqual(product.json()["sellerId"], seller["id"])
        self.approve_seller_product(product.json()["id"])
        self.assertEqual(
            self.client.get(f"/api/seller/stores/{seller['store_slug']}").status_code,
            200,
        )
        self.assertEqual(len(self.client.get("/api/seller/products").json()), 1)

        foreign_update = self.client.put(
            "/api/seller/products/perf-03",
            headers=self.seller_write_headers,
            json={
                "name": "Not owned",
                "brand": "Velvet Atelier",
                "sku": "VA-NOT-OWNED",
                "category": "Perfumes & Fragrances",
                "detail": "A product that belongs elsewhere",
                "description": "This update must not modify the platform catalog.",
                "price": 2000,
                "stock": 1,
                "images": ["https://images.example/rose.jpg"],
            },
        )
        self.assertEqual(foreign_update.status_code, 404)

    def test_seller_variants_bulk_catalog_contacts_and_holiday_mode(self) -> None:
        seller = self.register_seller(self.client, "Lumen Atelier")
        self.login_admin()
        self.approve_seller(seller["id"])
        created = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Lumen Eau de Parfum",
                "brand": "Lumen",
                "sku": "LUMEN-EDP-01",
                "category": "Perfumes & Fragrances",
                "detail": "A warm everyday fragrance",
                "description": "A warm everyday fragrance with soft floral and amber notes.",
                "price": 2000,
                "stock": 12,
                "images": ["https://images.example/lumen.jpg"],
                "variants": [{"name": "Size", "options": ["30ml", "50ml", "100ml"]}],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        product_id = created.json()["id"]
        self.assertEqual(created.json()["variants"][0]["options"], ["30ml", "50ml", "100ml"])
        self.approve_seller_product(product_id)

        updated_profile = self.client.put(
            "/api/seller/profile",
            headers=self.seller_write_headers,
            json={
                "store_name": seller["store_name"],
                "store_bio": "Fragrance made personal.",
                "business_category": "Perfumes & Fragrances",
                "logo_url": "",
                "banner_url": "",
                "business_phone": "+254700000000",
                "whatsapp_phone": "+254711111111",
                "instagram_url": "https://instagram.com/lumen",
                "tiktok_url": "https://tiktok.com/@lumen",
                "operating_hours": "Mon-Sat, 9:00-18:00",
                "holiday_mode": True,
                "payout_method": "M-Pesa",
                "payout_account": "+254700000000",
            },
        )
        self.assertEqual(updated_profile.status_code, 200, updated_profile.text)
        public = self.client.get(f"/api/sellers/{seller['store_slug']}")
        self.assertEqual(public.status_code, 200, public.text)
        payload = public.json()
        self.assertTrue(payload["verified"])
        self.assertEqual(payload["seller"]["business_phone"], "+254700000000")
        self.assertEqual(payload["seller"]["seller_phone"], "+254700000000")
        self.assertTrue(payload["seller"]["seller_verified"])
        self.assertEqual(payload["seller"]["whatsapp_phone"], "+254711111111")
        self.assertTrue(payload["seller"]["holiday_mode"])
        self.assertNotIn("payout_account", payload["seller"])
        self.assertNotIn("available_balance", payload["seller"])
        self.assertEqual(payload["products"][0]["variants"][0]["name"], "Size")
        listing = next(
            product for product in self.client.get("/api/products").json()
            if product["id"] == product_id
        )
        self.assertEqual(listing["seller"]["businessPhone"], "+254700000000")
        self.assertEqual(listing["seller"]["whatsappPhone"], "+254711111111")
        self.assertEqual(listing["seller_phone"], "+254700000000")
        self.assertEqual(listing["title"], "Lumen Eau de Parfum")
        self.assertNotIn("unitCost", listing)

        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            paused_checkout = self.client.post(
                "/api/orders/checkout",
                json={
                    "customer": {
                        "name": "Casey Buyer",
                        "phone": "+254700000003",
                        "address": "12 Market Road",
                    },
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "city": "Nairobi",
                    "mpesa_phone": "0712345678",
                },
            )
        self.assertEqual(paused_checkout.status_code, 409)
        self.assertIn("pausing new orders", paused_checkout.json()["detail"])

        archived = self.client.post(
            "/api/seller/products/bulk",
            headers=self.seller_write_headers,
            json={"product_ids": [product_id], "action": "status", "status": "ARCHIVED"},
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(archived.json()["products"][0]["status"], "ARCHIVED")
        out_of_stock = self.client.post(
            "/api/seller/products/bulk",
            headers=self.seller_write_headers,
            json={"product_ids": [product_id], "action": "out_of_stock"},
        )
        self.assertEqual(out_of_stock.status_code, 200, out_of_stock.text)
        self.assertEqual(out_of_stock.json()["products"][0]["stock"], 0)
        buyer_ids = {product["id"] for product in self.client.get("/api/products").json()}
        self.assertNotIn(product_id, buyer_ids)

    def test_seller_dispatch_route_and_small_demo_payout(self) -> None:
        seller = self.register_seller(self.client, "Juniper Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Juniper Daily Cream",
                "brand": "Juniper",
                "sku": "JUNIPER-CREAM-1",
                "category": "Skincare & Glow",
                "detail": "A nourishing daily cream",
                "description": "A gentle nourishing cream for a soft and hydrated complexion.",
                "price": 1000,
                "stock": 8,
                "images": ["https://images.example/juniper.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.approve_seller_product(product.json()["id"])
        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            checkout = self.client.post(
                "/api/orders/checkout",
                json={
                    "customer": {
                        "name": "Casey Buyer",
                        "phone": "+254700000003",
                        "address": "12 Market Road",
                    },
                    "items": [{"product_id": product.json()["id"], "quantity": 1}],
                    "city": "Nairobi",
                    "mpesa_phone": "0712345678",
                },
            )
        self.assertEqual(checkout.status_code, 201, checkout.text)
        order_id = self.client.get("/api/seller/orders").json()[0]["id"]
        for status_value, details in (
            ("PROCESSING", {}),
            ("SHIPPED", {"courier_name": "Fargo Courier", "tracking_number": "FG-12345"}),
            ("DELIVERED", {}),
        ):
            updated = self.client.put(
                f"/api/orders/{order_id}/status",
                headers=self.seller_write_headers,
                json={"status": status_value, **details},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
        seller_order = self.client.get("/api/seller/orders").json()[0]
        self.assertEqual(seller_order["courier_name"], "Fargo Courier")
        self.assertEqual(seller_order["tracking_number"], "FG-12345")
        partial = self.client.post(
            "/api/seller/withdraw",
            headers=self.seller_write_headers,
            json={"amount": 500, "destination_type": "paybill", "destination": "1234567"},
        )
        self.assertEqual(partial.status_code, 201, partial.text)
        self.assertEqual(partial.json()["amount"], 500)
        self.assertTrue(partial.json()["destination_hint"].endswith("4567"))
        self.assertEqual(self.client.get("/api/seller/dashboard").json()["available_balance"], 400)
        small_demo_payout = self.client.post(
            "/api/seller/withdraw",
            headers=self.seller_write_headers,
            json={"amount": 400, "destination_type": "registered_phone"},
        )
        self.assertEqual(small_demo_payout.status_code, 201, small_demo_payout.text)
        self.assertEqual(small_demo_payout.json()["amount"], 400)
        self.assertEqual(
            self.client.get("/api/seller/dashboard").json()["available_balance"], 0
        )
        below_minimum = self.client.post(
            "/api/seller/withdraw",
            headers=self.seller_write_headers,
            json={"amount": 0.5, "destination_type": "registered_phone"},
        )
        self.assertEqual(below_minimum.status_code, 422)

    def test_master_tracking_admin_override_and_seller_inspection(self) -> None:
        seller = self.register_seller(self.client, "Juniper Trust Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Juniper Trust Serum",
                "brand": "Juniper",
                "sku": "JUNIPER-TRUST-1",
                "category": "Skincare & Glow",
                "detail": "A verified daily serum",
                "description": "A lightweight daily serum for hydrated skin.",
                "price": 1200,
                "stock": 5,
                "images": ["https://images.example/juniper-trust.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.approve_seller_product(product.json()["id"])
        checkout = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Morgan Buyer",
                    "phone": "+254700000011",
                    "address": "4 Garden Avenue, Nairobi",
                },
                "items": [{"product_id": product.json()["id"], "quantity": 1}],
            },
        )
        self.assertEqual(checkout.status_code, 201, checkout.text)
        tracking_id = checkout.json()["tracking_id"]
        sub_order_id = self.client.get("/api/seller/orders").json()[0]["id"]

        with self.client.websocket_connect(f"/ws/orders/{tracking_id}") as socket:
            connected = socket.receive_json()
            self.assertEqual(connected["type"], "connected")
            packed = self.client.put(
                f"/api/seller/orders/{sub_order_id}/status",
                headers=self.seller_write_headers,
                json={"status": "PACKED_AND_READY"},
            )
            self.assertEqual(packed.status_code, 200, packed.text)
            self.assertEqual(socket.receive_json()["status"], "PACKED")
            dispatched = self.client.put(
                f"/api/seller/orders/{sub_order_id}/status",
                headers=self.seller_write_headers,
                json={
                    "status": "DISPATCHED_TO_COURIER",
                    "courier_name": "Fargo Courier",
                    "tracking_number": "FG-TRACK-5544",
                },
            )
            self.assertEqual(dispatched.status_code, 200, dispatched.text)
            self.assertEqual(socket.receive_json()["status"], "DISPATCHED_TO_COURIER")

            courier_lookup = self.client.get(
                "/api/orders/track/FG-TRACK-5544"
            )
            self.assertEqual(courier_lookup.status_code, 200, courier_lookup.text)
            self.assertEqual(courier_lookup.json()["packages"][0]["seller_name"], "Juniper Trust Studio")
            self.assertEqual(
                courier_lookup.json()["packages"][0]["tracking_number"],
                "FG-TRACK-5544",
            )

            admin_orders = self.client.get(
                "/api/admin/orders",
                params={
                    "scope": "fulfillment",
                    "status": "DISPATCHED_TO_COURIER",
                    "search": "FG-TRACK-5544",
                },
            )
            self.assertEqual(admin_orders.status_code, 200, admin_orders.text)
            self.assertEqual(len(admin_orders.json()), 1)
            self.assertEqual(admin_orders.json()[0]["tracking_id"], tracking_id)

            with closing(sqlite3.connect(self.database_path)) as connection:
                connection.execute(
                    "UPDATE orders SET payment_status = 'paid' WHERE order_number = ?",
                    (tracking_id,),
                )
                connection.execute(
                    "UPDATE sellers SET rating = 4.8 WHERE id = ?", (seller["id"],)
                )
                connection.execute(
                    """
                    INSERT INTO seller_reviews (
                        seller_id, sub_order_id, rating, comment
                    ) VALUES (?, ?, 5, 'Arrived carefully packed.')
                    """,
                    (seller["id"], sub_order_id),
                )
                connection.commit()

            override = self.client.put(
                f"/api/admin/orders/{sub_order_id}/override-status",
                headers=self.admin_write_headers,
                json={
                    "status": "DELIVERED",
                    "note": "Delivery confirmed by courier support.",
                },
            )
            self.assertEqual(override.status_code, 200, override.text)
            self.assertEqual(socket.receive_json()["status"], "DELIVERED")

        buyer_tracking = self.client.get(f"/api/orders/track/{tracking_id}")
        self.assertEqual(buyer_tracking.status_code, 200, buyer_tracking.text)
        self.assertEqual(buyer_tracking.json()["packages"][0]["status"], "DELIVERED")
        order_detail = self.client.get(f"/api/admin/orders/{sub_order_id}")
        self.assertEqual(order_detail.status_code, 200, order_detail.text)
        self.assertEqual(order_detail.json()["fulfillment_status"], "DELIVERED")
        inspection = self.client.get(
            "/api/sellers/inspect", params={"query": "Juniper Trust Studio"}
        )
        self.assertEqual(inspection.status_code, 200, inspection.text)
        self.assertTrue(inspection.json()["is_verified"])
        self.assertEqual(inspection.json()["fulfillment_rate"], 100)
        self.assertEqual(inspection.json()["reviews"][0]["comment"], "Arrived carefully packed.")

    def test_seller_development_approval_is_gated_and_synchronizes_profiles(self) -> None:
        seller = self.register_seller(self.client, "Saffron Studio")
        pending_seller = self.register_seller(self.client, "Mallow Beauty")
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "SELLER_DEMO_APPROVAL_ENABLED": "true"},
        ):
            blocked = self.client.put(
                "/api/seller/approve-self", headers=self.seller_write_headers
            )
        self.assertEqual(blocked.status_code, 404)

        with patch.dict(
            os.environ,
            {"APP_ENV": "development", "SELLER_DEMO_APPROVAL_ENABLED": "true"},
        ):
            approved = self.client.put(
                "/api/seller/approve-self", headers=self.seller_write_headers
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "APPROVED")
            all_approved = self.client.post(
                "/api/seller/approve-all", headers=self.seller_write_headers
            )
            self.assertEqual(all_approved.status_code, 200, all_approved.text)
            self.assertEqual(all_approved.json()["approved_count"], 1)
            with closing(sqlite3.connect(self.database_path)) as connection:
                status_rows = connection.execute(
                    """
                    SELECT s.status, sp.status
                    FROM sellers s JOIN seller_profiles sp ON sp.seller_id = s.id
                    WHERE s.id IN (?, ?)
                    ORDER BY s.id
                    """,
                    (seller["id"], pending_seller["id"]),
                ).fetchone()
                all_status_rows = connection.execute(
                    """
                    SELECT s.status, sp.status
                    FROM sellers s JOIN seller_profiles sp ON sp.seller_id = s.id
                    ORDER BY s.id
                    """
                ).fetchall()
            self.assertEqual(status_rows, ("APPROVED", "approved"))
            self.assertEqual(
                all_status_rows,
                [("APPROVED", "approved"), ("APPROVED", "approved")],
            )

    def test_development_can_auto_approve_new_seller_registrations(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "SELLER_DEMO_APPROVAL_ENABLED": "true",
                "SELLER_AUTO_APPROVE_REGISTRATIONS": "true",
            },
        ):
            seller = self.register_seller(self.client, "Orchid Development")
        self.assertEqual(seller["status"], "APPROVED")
        with closing(sqlite3.connect(self.database_path)) as connection:
            profile_status = connection.execute(
                "SELECT status FROM seller_profiles WHERE seller_id = ?",
                (seller["id"],),
            ).fetchone()[0]
        self.assertEqual(profile_status, "approved")

    def test_seller_image_upload_is_limited_to_public_raster_formats(self) -> None:
        seller = self.register_seller(self.client, "Clover Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        uploaded = self.client.post(
            "/api/seller/uploads",
            headers=self.seller_write_headers,
            files={"image": ("logo.png", b"\x89PNG\r\n\x1a\nimage-data", "image/png")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        uploaded_name = uploaded.json()["url"].rsplit("/", 1)[-1]
        try:
            served = self.client.get(f"/uploads/{uploaded_name}")
            self.assertEqual(served.status_code, 200)
            self.assertEqual(served.headers["content-type"], "image/png")
            rejected = self.client.post(
                "/api/seller/uploads",
                headers=self.seller_write_headers,
                files={"image": ("logo.svg", b"<svg></svg>", "image/svg+xml")},
            )
            self.assertEqual(rejected.status_code, 415)
        finally:
            (UPLOAD_ROOT / uploaded_name).unlink(missing_ok=True)

    def test_seller_plan_change_persists_plan_and_commission_rate(self) -> None:
        seller = self.register_seller(self.client, "Plan Change Studio")
        self.login_admin()
        self.approve_seller(seller["id"])

        updated = self.client.put(
            "/api/seller/plan",
            headers=self.seller_write_headers,
            json={"selected_plan": "enterprise"},
        )

        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["selected_plan"], "enterprise")
        self.assertEqual(updated.json()["commission_rate"], 2.5)
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT selected_plan, commission_rate FROM sellers WHERE id = ?",
                (seller["id"],),
            ).fetchone()
        self.assertEqual(row, ("enterprise", 2.5))

    def test_seller_portal_demo_checkout_payout_and_storefront_settings(self) -> None:
        seller = self.register_seller(self.client, "Cedar Glow Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        product_response = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Cedar Glow Serum",
                "brand": "Cedar Glow",
                "sku": "CG-SERUM-01",
                "category": "Skincare & Glow",
                "detail": "A soothing daily serum",
                "description": "A lightweight daily serum for a calm, hydrated skin routine.",
                "price": 1000,
                "stock": 10,
                "images": ["https://images.example/serum.jpg"],
                "tags": ["hydrating", "daily"],
            },
        )
        self.assertEqual(product_response.status_code, 201, product_response.text)
        self.assertEqual(product_response.json()["tags"], ["hydrating", "daily"])
        self.approve_seller_product(product_response.json()["id"])

        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            checkout = self.client.post(
                "/api/orders/checkout",
                json={
                    "customer": {
                        "name": "Casey Buyer",
                        "phone": "+254700000003",
                        "address": "12 Market Road",
                    },
                    "items": [{"product_id": product_response.json()["id"], "quantity": 1}],
                    "city": "Nairobi",
                    "delivery_notes": "Call at the gate",
                    "mpesa_phone": "0712345678",
                },
            )
        self.assertEqual(checkout.status_code, 201, checkout.text)
        self.assertEqual(checkout.json()["payment_status"], "COMPLETED (DEMO)")
        self.assertTrue(checkout.json()["master_tracking_id"])
        self.assertTrue(checkout.json()["transaction_reference"].startswith("MPESA-"))
        self.assertEqual(checkout.json()["sub_orders"][0]["store_name"], "Cedar Glow Studio")

        seller_order = self.client.get("/api/seller/orders").json()[0]
        self.assertEqual(seller_order["payment_status"], "completed_demo")
        self.assertEqual(seller_order["fulfillment_status"], "PENDING")
        self.assertEqual(seller_order["payout_status"], "ESCROW PAID (DEMO)")
        for fulfillment_status in ("PROCESSING", "SHIPPED", "DELIVERED"):
            updated = self.client.patch(
                f"/api/seller/orders/{seller_order['id']}",
                headers=self.seller_write_headers,
                json={"status": fulfillment_status},
            )
            self.assertEqual(updated.status_code, 200, updated.text)

        dashboard = self.client.get("/api/seller/dashboard").json()
        self.assertEqual(dashboard["gross_sales"], 1000)
        self.assertEqual(dashboard["available_balance"], 900)
        weekly_dashboard = self.client.get("/api/seller/dashboard?period=7d").json()
        self.assertEqual(weekly_dashboard["analytics_period"], "7d")
        self.assertEqual(len(weekly_dashboard["sales_series"]), 7)
        invalid_period = self.client.get("/api/seller/dashboard?period=quarter")
        self.assertEqual(invalid_period.status_code, 422)
        payout = self.client.post(
            "/api/seller/withdraw", headers=self.seller_write_headers
        )
        self.assertEqual(payout.status_code, 201, payout.text)
        self.assertTrue(payout.json()["is_demo"])
        self.assertEqual(payout.json()["amount"], 900)
        self.assertTrue(payout.json()["transaction_id"].startswith("SIMULATED-"))
        self.assertEqual(
            self.client.get("/api/seller/dashboard").json()["available_balance"], 0
        )
        self.assertEqual(len(self.client.get("/api/seller/payouts").json()), 1)

        settings = self.client.put(
            "/api/seller/profile",
            headers=self.seller_write_headers,
            json={
                "store_name": "Cedar Glow Atelier",
                "store_bio": "Carefully selected skincare essentials.",
                "business_category": "Skincare & Glow",
                "logo_url": "",
                "banner_url": "",
                "business_phone": "+254700000000",
                "payout_method": "M-Pesa",
                "payout_account": "+254700000000",
            },
        )
        self.assertEqual(settings.status_code, 200, settings.text)
        self.assertEqual(settings.json()["store_bio"], "Carefully selected skincare essentials.")
        public_store = self.client.get(
            f"/api/seller/stores/{seller['store_slug']}"
        ).json()["store"]
        self.assertEqual(public_store["store_name"], "Cedar Glow Atelier")
        self.assertEqual(public_store["store_bio"], "Carefully selected skincare essentials.")

    def test_seller_contact_changes_require_one_time_email_verification(self) -> None:
        seller = self.register_seller(self.client, "Verified Contact Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        profile_update = {
            "store_name": seller["store_name"],
            "store_bio": "",
            "business_category": "Beauty & Cosmetics",
            "logo_url": "",
            "banner_url": "",
            "business_phone": "0712345678",
            "payout_method": "M-Pesa",
            "payout_account": "0712345678",
        }
        bypass_attempt = self.client.put(
            "/api/seller/profile",
            headers=self.seller_write_headers,
            json=profile_update,
        )
        self.assertEqual(bypass_attempt.status_code, 409)

        with patch("app.routers.sellers._deliver_seller_update_code") as send_code:
            request_code = self.client.post(
                "/api/seller/request-profile-update",
                headers=self.seller_write_headers,
                json={
                    "new_email": "verified-contact@example.com",
                    "new_phone": "0712345678",
                },
            )
        self.assertEqual(request_code.status_code, 202, request_code.text)
        self.assertNotIn("code", request_code.json())
        code = send_code.call_args.args[1]
        incorrect_code = self.client.post(
            "/api/seller/verify-profile-update",
            headers=self.seller_write_headers,
            json={"code": "000000" if code != "000000" else "000001"},
        )
        self.assertEqual(incorrect_code.status_code, 400)
        verified = self.client.post(
            "/api/seller/verify-profile-update",
            headers=self.seller_write_headers,
            json={"code": code},
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(
            verified.json()["seller"]["email"], "verified-contact@example.com"
        )
        self.assertEqual(verified.json()["seller"]["business_phone"], "0712345678")

    def test_seller_advanced_tools_persist_and_enforce_ownership(self) -> None:
        seller = self.register_seller(self.client, "North Star Commerce")
        self.login_admin()
        self.approve_seller(seller["id"])
        campaign = self.client.post(
            "/api/admin/campaigns",
            headers=self.admin_write_headers,
            json={
                "title": "North Star Spotlight",
                "discount_percent": 15,
                "stock_allocation": 25,
                "duration_minutes": 120,
            },
        )
        self.assertEqual(campaign.status_code, 201, campaign.text)
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "North Star Daily Serum",
                "brand": "North Star",
                "sku": "NS-SERUM-01",
                "category": "Health & Personal Care",
                "detail": "A lightweight daily hydration serum",
                "description": "A lightweight daily hydration serum for a comfortable finish.",
                "price": 1200,
                "stock": 10,
                "images": ["https://images.example/north-star-serum.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        product_id = product.json()["id"]
        self.approve_seller_product(product_id)

        enrollment = self.client.post(
            f"/api/seller/campaigns/{campaign.json()['id']}/enroll",
            headers=self.seller_write_headers,
            json={"product_ids": [product_id]},
        )
        self.assertEqual(enrollment.status_code, 200, enrollment.text)
        available_campaigns = self.client.get("/api/seller/campaigns").json()
        self.assertTrue(available_campaigns[0]["enrolled"])
        self.assertEqual(available_campaigns[0]["product_ids"], [product_id])

        health = self.client.get("/api/seller/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["average_rating"], 0)

        promotion = self.client.post(
            "/api/promotions",
            headers=self.seller_write_headers,
            json={
                "promotion_type": "flash_sale",
                "name": "North Star Weekend Sale",
                "product_ids": [product_id],
                "discount_percent": 20,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            },
        )
        self.assertEqual(promotion.status_code, 201, promotion.text)
        self.assertEqual(
            self.client.get(f"/api/products/{product_id}").json()["price"], 960
        )
        overlapping_promotion = self.client.post(
            "/api/promotions",
            headers=self.seller_write_headers,
            json={
                "promotion_type": "price_discount",
                "name": "Overlapping sale",
                "product_ids": [product_id],
                "discount_percent": 10,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            },
        )
        self.assertEqual(overlapping_promotion.status_code, 409)

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE seller_promotions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                (promotion.json()["id"],),
            )
            connection.commit()
        expired_product = self.client.get(f"/api/products/{product_id}")
        self.assertEqual(expired_product.json()["price"], 1200)

        csv_content = (
            "name,brand,sku,category,detail,description,price,stock,images,tags,variants\r\n"
            "North Star Travel Bottle,North Star,NS-BOTTLE-01,Travel & Luggage,"
            "Insulated travel bottle,A reusable insulated bottle for daily travel.,850,18,"
            "https://images.example/bottle.jpg,travel|reusable,Size: 500ml\r\n"
        )
        imported = self.client.post(
            "/api/products/bulk-upload",
            headers=self.seller_write_headers,
            files={"file": ("catalog.csv", csv_content.encode(), "text/csv")},
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["created"], 1)

        with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
            checkout = self.client.post(
                "/api/orders/checkout",
                json={
                    "customer": {
                        "name": "Casey Buyer",
                        "phone": "+254700000003",
                        "address": "12 Market Road, Nairobi",
                    },
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "city": "Nairobi",
                    "mpesa_phone": "0712345678",
                },
            )
        self.assertEqual(checkout.status_code, 201, checkout.text)
        sub_order_id = checkout.json()["sub_orders"][0]["sub_order_id"]
        for fulfillment_status, dispatch in [
            ("PACKED_AND_READY", {}),
            (
                "DISPATCHED_TO_COURIER",
                {"courier_name": "Fargo Courier", "tracking_number": "FARGO-9921"},
            ),
            ("DELIVERED_TO_CUSTOMER", {}),
        ]:
            updated = self.client.put(
                f"/api/orders/{sub_order_id}/status",
                headers=self.seller_write_headers,
                json={"status": fulfillment_status, **dispatch},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
        return_request = self.client.post(
            "/api/returns",
            json={
                "sub_order_id": sub_order_id,
                "order_number": checkout.json()["order_number"],
                "customer_phone": "+254700000003",
                "reason": "The parcel arrived with damaged packaging.",
            },
        )
        self.assertEqual(return_request.status_code, 201, return_request.text)
        return_update = self.client.put(
            f"/api/returns/{return_request.json()['id']}",
            headers=self.seller_write_headers,
            json={
                "action": "replacement_offered",
                "resolution_note": "Replacement approved for dispatch.",
            },
        )
        self.assertEqual(return_update.status_code, 200, return_update.text)
        self.assertEqual(return_update.json()["status"], "REPLACEMENT_OFFERED")

        self.assertEqual(
            self.client.get("/api/seller/returns").json()[0]["status"],
            "REPLACEMENT_OFFERED",
        )

        boost = self.client.post(
            "/api/products/boost",
            headers=self.seller_write_headers,
            json={"product_id": product_id, "duration_days": 3, "amount": 500},
        )
        self.assertEqual(boost.status_code, 201, boost.text)
        self.assertTrue(boost.json()["is_simulated"])
        boosted_product = self.client.get(f"/api/products/{product_id}").json()
        self.assertTrue(boosted_product["sponsored"])
        self.assertEqual(boosted_product["tag"], "SPONSORED")
        ads = self.client.get("/api/seller/ads")
        self.assertEqual(ads.status_code, 200, ads.text)
        self.assertEqual(ads.json()["available_balance"], 580)
        self.assertEqual(
            self.client.get("/api/seller/dashboard").json()["available_balance"], 580
        )
        payout = self.client.post(
            "/api/seller/withdraw",
            headers=self.seller_write_headers,
            json={
                "amount": 580,
                "destination_type": "registered_phone",
            },
        )
        self.assertEqual(payout.status_code, 201, payout.text)
        self.assertEqual(
            self.client.get("/api/seller/dashboard").json()["available_balance"], 0
        )

    def test_multi_vendor_checkout_splits_commission_and_records_payout_once(self) -> None:
        first_seller = self.register_seller(self.client, "Cedar House")
        with TestClient(create_app()) as second_client:
            second_seller = self.register_seller(second_client, "Petal Studio")
            self.login_admin()
            self.approve_seller(first_seller["id"])
            self.approve_seller(second_seller["id"])

            seller_product = {
                "brand": "Marketplace",
                "category": "Skincare & Glow",
                "detail": "A nourishing daily skincare treatment",
                "description": "A nourishing daily skincare treatment for soft, hydrated skin.",
                "price": 1000,
                "stock": 10,
                "images": ["https://images.example/marketplace.jpg"],
            }
            first_product = self.client.post(
                "/api/seller/products",
                headers=self.seller_write_headers,
                json={**seller_product, "name": "Cedar Cream", "sku": "CEDAR-01"},
            )
            second_product = second_client.post(
                "/api/seller/products",
                headers=self.seller_write_headers,
                json={**seller_product, "name": "Petal Serum", "sku": "PETAL-01"},
            )
            self.assertEqual(first_product.status_code, 201, first_product.text)
            self.assertEqual(second_product.status_code, 201, second_product.text)
            self.approve_seller_product(first_product.json()["id"])
            self.approve_seller_product(second_product.json()["id"])

            order_response = self.client.post(
                "/api/orders",
                json={
                    "customer": {
                        "name": "Jamie Rivers",
                        "phone": "+1 555 123 4567",
                        "address": "18 Garden Lane, Portland",
                    },
                    "items": [
                        {"product_id": first_product.json()["id"], "quantity": 1},
                        {"product_id": second_product.json()["id"], "quantity": 1},
                    ],
                },
            )
            self.assertEqual(order_response.status_code, 201, order_response.text)
            with closing(sqlite3.connect(self.database_path)) as connection:
                sub_orders = connection.execute(
                    """
                    SELECT seller_id, subtotal, commission_amount, seller_payout_amount
                    FROM sub_orders ORDER BY seller_id
                    """
                ).fetchall()
                connection.execute(
                    """
                    UPDATE orders SET payment_status = 'paid'
                    WHERE order_number = ?
                    """,
                    (order_response.json()["order_number"],),
                )
                connection.execute("UPDATE sub_orders SET fulfillment_status = 'DELIVERED'")
                connection.commit()
            self.assertEqual(len(sub_orders), 2)
            self.assertEqual(
                [(row[1], row[2], row[3]) for row in sub_orders],
                [(1000, 100, 900), (1000, 100, 900)],
            )
            self.assertEqual(len(self.client.get("/api/seller/orders").json()), 1)
            self.assertEqual(len(second_client.get("/api/seller/orders").json()), 1)
            marketplace_orders = self.client.get("/api/admin/marketplace/orders")
            self.assertEqual(marketplace_orders.status_code, 200, marketplace_orders.text)
            self.assertEqual(len(marketplace_orders.json()), 2)

            marketplace = self.client.get("/api/admin/marketplace")
            self.assertEqual(marketplace.status_code, 200, marketplace.text)
            self.assertEqual(marketplace.json()["total_commissions"], 200)
            payout_response = self.client.post(
                "/api/admin/marketplace/payouts",
                headers=self.admin_write_headers,
                json={
                    "seller_id": first_seller["id"],
                    "sub_order_ids": [1],
                    "reference": "MPESA-RECEIPT-001",
                },
            )
            self.assertEqual(payout_response.status_code, 201, payout_response.text)
            self.assertEqual(payout_response.json()["amount"], 900)
            self.assertEqual(payout_response.json()["status"], "PROCESSING")
            payout_complete = self.client.patch(
                f"/api/admin/marketplace/payouts/{payout_response.json()['id']}",
                headers=self.admin_write_headers,
                json={
                    "status": "COMPLETED",
                    "transaction_id": "MPESA-TRANSFER-001",
                },
            )
            self.assertEqual(payout_complete.status_code, 200, payout_complete.text)
            self.assertEqual(payout_complete.json()["status"], "COMPLETED")
            duplicate_payout = self.client.post(
                "/api/admin/marketplace/payouts",
                headers=self.admin_write_headers,
                json={
                    "seller_id": first_seller["id"],
                    "sub_order_ids": [1],
                    "reference": "MPESA-RECEIPT-002",
                },
            )
            self.assertEqual(duplicate_payout.status_code, 409)

            with patch.dict(os.environ, {"DEMO_CHECKOUT_ENABLED": "true"}):
                demo_checkout = self.client.post(
                    "/api/orders/checkout",
                    json={
                        "customer": {
                            "name": "Jamie Rivers",
                            "phone": "+1 555 123 4567",
                            "address": "18 Garden Lane",
                        },
                        "items": [
                            {"product_id": first_product.json()["id"], "quantity": 1},
                            {"product_id": second_product.json()["id"], "quantity": 1},
                        ],
                        "city": "Nairobi",
                        "delivery_notes": "",
                        "mpesa_phone": "0712345678",
                    },
                )
            self.assertEqual(demo_checkout.status_code, 201, demo_checkout.text)
            self.assertEqual(len(demo_checkout.json()["sub_orders"]), 2)
            self.assertEqual(
                [item["net_amount"] for item in demo_checkout.json()["sub_orders"]],
                [900, 900],
            )
            with closing(sqlite3.connect(self.database_path)) as connection:
                ledger_rows = connection.execute(
                    """
                    SELECT status, net_amount FROM seller_payout_ledger
                    ORDER BY seller_id
                    """
                ).fetchall()
            self.assertEqual(
                ledger_rows,
                [("ESCROW PAID (DEMO)", 900), ("ESCROW PAID (DEMO)", 900)],
            )

    def test_admin_can_record_complaint_warning_and_reports_email_delivery_state(self) -> None:
        seller = self.register_seller(self.client, "Rosewood Market")
        self.login_admin()
        with patch.dict(
            os.environ,
            {
                "RESEND_API_KEY": "",
                "RESEND_FROM_EMAIL": "",
                "SMTP_HOST": "",
                "SMTP_FROM": "",
            },
        ):
            warning = self.client.post(
                f"/api/admin/marketplace/vendors/{seller['id']}/warnings",
                headers=self.admin_write_headers,
                json={
                    "complaint_summary": "Buyer reports that the delivered item was damaged.",
                    "complaint_reference": "ORDER-123",
                },
            )
        self.assertEqual(warning.status_code, 200, warning.text)
        self.assertEqual(warning.json()["delivery_status"], "NOT_CONFIGURED")
        self.assertEqual(warning.json()["complaint_reference"], "ORDER-123")
        history = self.client.get(
            f"/api/admin/marketplace/vendors/{seller['id']}/warnings",
            headers=self.admin_write_headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()), 1)

    def test_admin_warning_sends_mail_when_smtp_is_configured(self) -> None:
        seller = self.register_seller(self.client, "Juniper Market")
        self.login_admin()
        with (
            patch.dict(
                os.environ,
                {
                    "SMTP_HOST": "smtp.example.test",
                    "SMTP_PORT": "587",
                    "SMTP_USERNAME": "",
                    "SMTP_PASSWORD": "",
                    "SMTP_FROM": "support@example.test",
                    "SMTP_STARTTLS": "false",
                    "RESEND_API_KEY": "",
                    "RESEND_FROM_EMAIL": "",
                },
            ),
            patch("app.email_delivery.smtplib.SMTP") as smtp_client,
        ):
            smtp_client.return_value.__enter__.return_value.send_message.return_value = {}
            warning = self.client.post(
                f"/api/admin/marketplace/vendors/{seller['id']}/warnings",
                headers=self.admin_write_headers,
                json={
                    "complaint_summary": "Buyer reports that the delivered item was damaged.",
                },
            )
        self.assertEqual(warning.status_code, 200, warning.text)
        self.assertEqual(warning.json()["delivery_status"], "SENT")
        smtp_client.return_value.__enter__.return_value.send_message.assert_called_once()

    def test_admin_warning_sends_through_resend(self) -> None:
        seller = self.register_seller(self.client, "Cedar House")
        self.login_admin()
        response = Mock(status_code=200)
        with (
            patch.dict(
                os.environ,
                {
                    "RESEND_API_KEY": "test-resend-key",
                    "RESEND_FROM_EMAIL": "Maison Muse <support@example.test>",
                    "SMTP_HOST": "",
                    "SMTP_FROM": "",
                },
            ),
            patch("app.email_delivery.httpx.post", return_value=response) as resend_post,
        ):
            warning = self.client.post(
                f"/api/admin/marketplace/vendors/{seller['id']}/warnings",
                headers=self.admin_write_headers,
                json={
                    "complaint_summary": "Buyer reports that the delivered item was damaged.",
                },
            )
        self.assertEqual(warning.status_code, 200, warning.text)
        self.assertEqual(warning.json()["delivery_status"], "SENT")
        resend_post.assert_called_once()
        self.assertEqual(
            resend_post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-resend-key",
        )

    def test_suspended_seller_has_reason_but_no_seller_api_access(self) -> None:
        seller = self.register_seller(self.client, "Cedar & Rose")
        self.login_admin()
        suspended = self.client.post(
            f"/api/admin/marketplace/vendors/{seller['id']}/review",
            headers=self.admin_write_headers,
            json={"action": "SUSPEND", "reason": "Repeated verified delivery complaints."},
        )
        self.assertEqual(suspended.status_code, 200, suspended.text)

        profile = self.client.get("/api/seller/me")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["status"], "SUSPENDED")
        self.assertEqual(profile.json()["review_note"], "Repeated verified delivery complaints.")

        blocked = self.client.get("/api/seller/orders")
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertIn("Repeated verified delivery complaints.", blocked.json()["detail"])

        signed_out = self.client.post(
            "/api/seller/logout",
            headers=self.seller_write_headers,
        )
        self.assertEqual(signed_out.status_code, 200, signed_out.text)

    def test_admin_can_enable_and_end_seller_maintenance(self) -> None:
        seller = self.register_seller(self.client, "Cedar Rose Boutique")
        self.login_admin()
        approved = self.client.patch(
            f"/api/admin/marketplace/vendors/{seller['id']}",
            headers=self.admin_write_headers,
            json={"status": "APPROVED"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Cedar Face Oil",
                "brand": "Cedar Rose Boutique",
                "sku": "CR-FACE-01",
                "category": "Skincare & Glow",
                "detail": "A lightweight facial oil",
                "description": "A lightweight facial oil for daily use.",
                "price": 1800,
                "stock": 5,
                "images": ["https://images.example/cedar-oil.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        quality_review = self.client.post(
            f"/api/admin/seller-qc/{product.json()['id']}",
            headers=self.admin_write_headers,
            json={"action": "APPROVE", "notes": "Listing checked."},
        )
        self.assertEqual(quality_review.status_code, 200, quality_review.text)
        self.assertIn(
            product.json()["id"],
            {item["id"] for item in self.client.get("/api/products").json()},
        )

        invalid = self.client.patch(
            f"/api/admin/marketplace/vendors/{seller['id']}/maintenance",
            headers=self.admin_write_headers,
            json={"enabled": True, "reason": "  "},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)
        enabled = self.client.patch(
            f"/api/admin/marketplace/vendors/{seller['id']}/maintenance",
            headers=self.admin_write_headers,
            json={"enabled": True, "reason": "Compliance review in progress."},
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        profile = self.client.get("/api/seller/me")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertTrue(profile.json()["maintenance_mode"])
        self.assertEqual(profile.json()["maintenance_reason"], "Compliance review in progress.")
        self.assertNotIn(
            product.json()["id"],
            {item["id"] for item in self.client.get("/api/products").json()},
        )
        store = self.client.get(f"/api/sellers/stores/{seller['store_slug']}")
        self.assertEqual(store.status_code, 404, store.text)
        blocked = self.client.delete(
            f"/api/seller/products/{product.json()['id']}",
            headers=self.seller_write_headers,
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        self.assertIn("Compliance review in progress.", blocked.json()["detail"])
        dashboard = self.client.get("/api/seller/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)

        ended = self.client.patch(
            f"/api/admin/marketplace/vendors/{seller['id']}/maintenance",
            headers=self.admin_write_headers,
            json={"enabled": False},
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertFalse(ended.json()["maintenance_mode"])
        self.assertIn(
            product.json()["id"],
            {item["id"] for item in self.client.get("/api/products").json()},
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            audit_events = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT event_type FROM admin_audit_logs
                    WHERE event_type IN (
                        'VENDOR_MAINTENANCE_ENABLED',
                        'VENDOR_MAINTENANCE_ENDED'
                    )
                    """
                )
            }
        self.assertEqual(
            audit_events,
            {"VENDOR_MAINTENANCE_ENABLED", "VENDOR_MAINTENANCE_ENDED"},
        )

    def test_global_seller_portal_maintenance_blocks_all_seller_access(self) -> None:
        seller = self.register_seller(self.client, "Global Portal Boutique")
        self.login_admin()

        invalid = self.client.patch(
            "/api/admin/marketplace/seller-portal-maintenance",
            headers=self.admin_write_headers,
            json={"enabled": True, "reason": "  "},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)
        enabled = self.client.patch(
            "/api/admin/marketplace/seller-portal-maintenance",
            headers=self.admin_write_headers,
            json={"enabled": True, "reason": "Platform upgrade in progress."},
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)
        self.assertEqual(
            enabled.json(),
            {"enabled": True, "reason": "Platform upgrade in progress."},
        )
        self.assertEqual(
            self.client.get("/api/seller/portal-status").json(),
            {"enabled": True, "reason": "Platform upgrade in progress."},
        )

        profile = self.client.get("/api/seller/me")
        self.assertEqual(profile.status_code, 503, profile.text)
        self.assertIn("Platform upgrade in progress.", profile.json()["detail"])
        seller_login = self.client.post(
            "/api/seller/login",
            headers=self.seller_write_headers,
            json={"email": seller["email"], "password": "correct-horse-battery"},
        )
        self.assertEqual(seller_login.status_code, 503, seller_login.text)
        auth_login = self.client.post(
            "/api/auth/login",
            json={"email": seller["email"], "password": "correct-horse-battery"},
        )
        self.assertEqual(auth_login.status_code, 503, auth_login.text)
        seller_registration = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "New Seller",
                "email": "new-maintenance-seller@example.com",
                "password": "another-secure-password",
                "role": "seller",
                "phone": "+254700000004",
                "store_name": "New Store",
                "business_type": "Beauty & Personal Care Cosmetics",
                "business_category": "Skincare & Glow",
                "city": "Nairobi",
                "payout_number": "254700000004",
                "national_id": "PVT-2026-0042",
                "accepted_terms": True,
                "selected_plan": "boutique",
            },
        )
        self.assertEqual(seller_registration.status_code, 503, seller_registration.text)
        seller_portal_registration = self.client.post(
            "/api/seller/register",
            headers=self.seller_write_headers,
            json={
                "email": "new-portal-seller@example.com",
                "password": "another-secure-password",
                "store_name": "New Portal Store",
                "owner_name": "New Seller",
                "business_type": "Beauty & Personal Care Cosmetics",
                "business_category": "Skincare & Glow",
                "logo_url": "",
                "banner_url": "",
                "business_phone": "+254700000005",
                "payout_method": "M-Pesa",
                "payout_account": "254700000005",
                "submitted_documents": [],
            },
        )
        self.assertEqual(
            seller_portal_registration.status_code, 503, seller_portal_registration.text
        )

        admin_marketplace = self.client.get("/api/admin/marketplace")
        self.assertEqual(admin_marketplace.status_code, 200, admin_marketplace.text)
        self.assertTrue(admin_marketplace.json()["seller_portal_maintenance_enabled"])

        disabled = self.client.patch(
            "/api/admin/marketplace/seller-portal-maintenance",
            headers=self.admin_write_headers,
            json={"enabled": False},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json(), {"enabled": False, "reason": ""})
        self.assertEqual(self.client.get("/api/seller/me").status_code, 200)
        with closing(sqlite3.connect(self.database_path)) as connection:
            audit_events = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT event_type FROM admin_audit_logs
                    WHERE event_type IN (
                        'SELLER_PORTAL_MAINTENANCE_ENABLED',
                        'SELLER_PORTAL_MAINTENANCE_DISABLED'
                    )
                    """
                )
            }
        self.assertEqual(
            audit_events,
            {
                "SELLER_PORTAL_MAINTENANCE_ENABLED",
                "SELLER_PORTAL_MAINTENANCE_DISABLED",
            },
        )

    def test_seller_review_commission_policy_dispute_and_audit(self) -> None:
        seller = self.register_seller(self.client, "Rosewood Market")
        self.login_admin()
        request_info = self.client.post(
            f"/api/admin/marketplace/vendors/{seller['id']}/review",
            headers=self.admin_write_headers,
            json={"action": "REQUEST_INFO", "reason": "Please provide a current business permit."},
        )
        self.assertEqual(request_info.status_code, 200, request_info.text)
        self.assertEqual(request_info.json()["status"], "PENDING")
        approved = self.client.post(
            f"/api/admin/marketplace/vendors/{seller['id']}/review",
            headers=self.admin_write_headers,
            json={"action": "APPROVE", "reason": "Documents verified."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        commission_update = self.client.put(
            "/api/admin/marketplace/commissions",
            headers=self.admin_write_headers,
            json={
                "default_percentage": 12,
                "category_rates": {"Perfumes & Fragrances": 8},
                "seller_rates": {str(seller["id"]): 9},
                "seller_category_rates": {
                    str(seller["id"]): {"Perfumes & Fragrances": 7}
                },
            },
        )
        self.assertEqual(commission_update.status_code, 200, commission_update.text)
        self.assertEqual(
            self.client.get("/api/admin/marketplace/commissions").json()[
                "seller_category_rates"
            ],
            [
                {
                    "seller_id": seller["id"],
                    "category": "Perfumes & Fragrances",
                    "percentage": 7,
                }
            ],
        )
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Rosewood Eau de Parfum",
                "brand": "Rosewood Market",
                "sku": "ROSEWOOD-EDP",
                "category": "Perfumes & Fragrances",
                "detail": "A warm rosewood fragrance",
                "description": "A carefully blended warm rosewood fragrance for everyday wear.",
                "price": 2000,
                "stock": 10,
                "images": ["https://images.example/rosewood.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.approve_seller_product(product.json()["id"])
        order = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [{"product_id": product.json()["id"], "quantity": 1}],
            },
        )
        self.assertEqual(order.status_code, 201, order.text)
        with closing(sqlite3.connect(self.database_path)) as connection:
            sub_order_id = connection.execute(
                "SELECT id FROM sub_orders"
            ).fetchone()[0]
        dispute = self.client.post(
            f"/api/admin/marketplace/orders/{sub_order_id}/disputes",
            headers=self.admin_write_headers,
            json={
                "action": "PENALTY_RECORDED",
                "reason": "Seller missed the dispatch deadline.",
                "amount": 250,
            },
        )
        self.assertEqual(dispute.status_code, 201, dispute.text)
        orders = self.client.get("/api/admin/marketplace/orders")
        self.assertEqual(len(orders.json()[0]["disputes"]), 1)
        with closing(sqlite3.connect(self.database_path)) as connection:
            commission_amount = connection.execute(
                "SELECT commission_amount FROM sub_orders"
            ).fetchone()[0]
            audit_events = {
                row[0]
                for row in connection.execute(
                    "SELECT event_type FROM admin_audit_logs WHERE event_category = 'Marketplace'"
                )
            }
        self.assertEqual(commission_amount, 140)
        self.assertTrue(
            {
                "VENDOR_INFO_REQUESTED",
                "VENDOR_APPROVED",
                "COMMISSION_SETTINGS_UPDATED",
                "MARKETPLACE_DISPUTE_ACTION",
            }.issubset(audit_events)
        )
        analytics = self.client.get("/api/admin/marketplace/analytics")
        self.assertEqual(analytics.status_code, 200, analytics.text)
        self.assertEqual(analytics.json()["active_sellers"], 1)

    def test_order_uses_server_prices_and_starts_pesapal_checkout(self) -> None:
        response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [
                    {
                        "product_id": "perf-03",
                        "quantity": 1,
                        "variant": "",
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        order = response.json()
        self.assertEqual(order["subtotal"], 3200)
        self.assertEqual(order["shipping"], 250)
        self.assertEqual(order["tax"], 256)
        self.assertEqual(order["total"], 3706)
        self.assertEqual(order["currency"], "KES")
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["payment_status"], "pending_callback")
        self.assertEqual(order["payment_gateway"], "Pesapal")
        self.assertTrue(order["redirect_url"].startswith("https://cybqa.pesapal.com/"))
        self.assertIn("order_number", order)
        with closing(sqlite3.connect(self.database_path)) as connection:
            saved_order = connection.execute(
                "SELECT order_number, total_cents, payment_method, gateway_tracking_id FROM orders"
            ).fetchone()
        self.assertEqual(
            saved_order,
            (
                order["order_number"],
                370600,
                "pesapal",
                f"tracking-{order['order_number']}",
            ),
        )

    def test_orders_above_free_shipping_threshold_have_no_shipping_fee(self) -> None:
        response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [
                    {
                        "product_id": "skin-01",
                        "quantity": 2,
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["subtotal"], 10800)
        self.assertEqual(response.json()["shipping"], 0)
        self.assertEqual(response.json()["tax"], 864)

    def test_pesapal_return_verifies_tracking_id_amount_and_currency(self) -> None:
        order_response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [{"product_id": "perf-03", "quantity": 1}],
            },
        )
        order = order_response.json()
        tracking_id = f"tracking-{order['order_number']}"

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "KES",
                "merchant_reference": order["order_number"],
                "payment_status_description": "Completed",
                "confirmation_code": "PESAPAL-RECEIPT",
            },
        ):
            verified = self.client.get(
                "/api/payments/pesapal/status",
                params={
                    "order_tracking_id": tracking_id,
                    "merchant_reference": order["order_number"],
                },
            )

        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["payment_status"], "paid")
        with closing(sqlite3.connect(self.database_path)) as connection:
            paid_order = connection.execute(
                "SELECT payment_status, gateway_reference FROM orders WHERE order_number = ?",
                (order["order_number"],),
            ).fetchone()
        self.assertEqual(paid_order, ("paid", "PESAPAL-RECEIPT"))

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "KES",
                "merchant_reference": order["order_number"],
                "payment_status_description": "Pending",
            },
        ):
            stale_pending = self.client.get(
                "/api/payments/pesapal/status",
                params={
                    "order_tracking_id": tracking_id,
                    "merchant_reference": order["order_number"],
                },
            )
        self.assertEqual(stale_pending.status_code, 200, stale_pending.text)
        self.assertEqual(stale_pending.json()["payment_status"], "paid")

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 1,
                "currency": "KES",
                "merchant_reference": order["order_number"],
                "payment_status_description": "Completed",
            },
        ):
            mismatched_amount = self.client.get(
                "/api/payments/pesapal/status",
                params={
                    "order_tracking_id": tracking_id,
                    "merchant_reference": order["order_number"],
                },
            )
        self.assertEqual(mismatched_amount.status_code, 409)

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "UGX",
                "merchant_reference": order["order_number"],
                "payment_status_description": "Completed",
            },
        ):
            mismatched_currency = self.client.get(
                "/api/payments/pesapal/status",
                params={
                    "order_tracking_id": tracking_id,
                    "merchant_reference": order["order_number"],
                },
            )
        self.assertEqual(mismatched_currency.status_code, 409)

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "KES",
                "merchant_reference": "MM-WRONG-ORDER",
                "payment_status_description": "Completed",
            },
        ):
            mismatched_reference = self.client.get(
                "/api/payments/pesapal/status",
                params={
                    "order_tracking_id": tracking_id,
                    "merchant_reference": order["order_number"],
                },
            )
        self.assertEqual(mismatched_reference.status_code, 409)

        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "KES",
                "merchant_reference": order["order_number"],
                "payment_status_description": "Completed",
                "confirmation_code": "PESAPAL-RECEIPT",
            },
        ):
            ipn = self.client.get(
                "/api/payments/pesapal/ipn",
                params={
                    "OrderNotificationType": "IPNCHANGE",
                    "OrderTrackingId": tracking_id,
                    "OrderMerchantReference": order["order_number"],
                },
            )
        self.assertEqual(ipn.status_code, 200, ipn.text)
        self.assertEqual(ipn.json()["status"], 200)
    def test_order_rejects_unknown_products_and_insufficient_stock(self) -> None:
        base_order = {
            "customer": {
                "name": "Jamie Rivers",
                "phone": "+1 555 123 4567",
                "address": "18 Garden Lane, Portland",
            },
        }
        unknown = self.client.post(
            "/api/orders",
            json={
                **base_order,
                "items": [{"product_id": "unknown", "quantity": 1}],
            },
        )
        out_of_stock = self.client.post(
            "/api/orders",
            json={
                **base_order,
                "items": [
                    {"product_id": "perf-03", "quantity": 99}
                ],
            },
        )

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(out_of_stock.status_code, 409)

    def test_invalid_customer_data_is_rejected(self) -> None:
        response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie",
                    "phone": "123",
                    "address": "Short",
                },
                "items": [{"product_id": "rose-oud-eau-de-parfum", "quantity": 1}],
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_newsletter_signup_is_normalized_and_persisted_idempotently(self) -> None:
        first_response = self.client.post(
            "/api/newsletter",
            json={"email": "  Beauty.Fan@Example.com "},
        )
        duplicate_response = self.client.post(
            "/api/newsletter",
            json={"email": "beauty.fan@example.com"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json(), duplicate_response.json())
        with closing(sqlite3.connect(self.database_path)) as connection:
            subscribers = connection.execute(
                "SELECT email FROM newsletter_subscribers"
            ).fetchall()
        self.assertEqual(subscribers, [("beauty.fan@example.com",)])

    def test_newsletter_signup_rejects_invalid_email(self) -> None:
        response = self.client.post(
            "/api/newsletter",
            json={"email": "not-an-email"},
        )

        self.assertEqual(response.status_code, 422)

    def test_admin_requires_login_and_validates_credentials(self) -> None:
        unauthorized = self.client.get("/api/admin/overview")
        failed_login = self.client.post(
            "/api/admin/login",
            json={"username": "store-admin", "password": "incorrect"},
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(failed_login.status_code, 401)
        self.login_admin()
        self.assertTrue(self.client.get("/api/admin/overview").json()["kpis"])

    def test_admin_product_crud_duplicate_and_inventory(self) -> None:
        self.login_admin()
        payload = {
            "name": "Admin Test Eau de Parfum",
            "brand": "Maison Muse",
            "sku": "ADMIN-PERF-01",
            "category": "Perfumes & Fragrances",
            "detail": "A warm floral scent",
            "description": "A soft floral fragrance made for everyday wear.",
            "price": 3500,
            "oldPrice": 4200,
            "stock": 9,
            "lowStockThreshold": 3,
            "tag": "BEST SELLER",
            "tagColor": "bg-rose-600",
            "images": ["https://images.unsplash.com/photo-1594035910387-fea47794261f"],
            "details": {"scentNotes": "rose, amber"},
        }
        rejected_write = self.client.post("/api/admin/products", json=payload)
        created = self.client.post(
            "/api/admin/products",
            json=payload,
            headers=self.admin_write_headers,
        )

        self.assertEqual(rejected_write.status_code, 403)
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        self.assertEqual(product["sku"], "ADMIN-PERF-01")
        self.assertEqual(product["lowStockThreshold"], 3)

        updated_payload = {**payload, "name": "Updated Eau de Parfum", "price": 3900}
        updated = self.client.put(
            f"/api/admin/products/{product['id']}",
            json=updated_payload,
            headers=self.admin_write_headers,
        )
        duplicated = self.client.post(
            f"/api/admin/products/{product['id']}/duplicate",
            headers=self.admin_write_headers,
        )
        out_of_stock = self.client.patch(
            f"/api/admin/products/{product['id']}/stock?stock=0",
            headers=self.admin_write_headers,
        )

        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Updated Eau de Parfum")
        self.assertEqual(updated.json()["price"], 3900)
        self.assertEqual(duplicated.status_code, 201, duplicated.text)
        self.assertTrue(duplicated.json()["sku"].startswith("ADMIN-PERF-01-COPY-"))
        self.assertEqual(out_of_stock.status_code, 200, out_of_stock.text)
        self.assertFalse(out_of_stock.json()["inStock"])

        deleted = self.client.delete(
            f"/api/admin/products/{product['id']}",
            headers=self.admin_write_headers,
        )
        hidden = self.client.get(f"/api/products/{product['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(hidden.status_code, 404)

    def test_admin_order_fulfillment_and_analytics_reflect_status(self) -> None:
        order_response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [{"product_id": "perf-03", "quantity": 1}],
            },
        )
        self.assertEqual(order_response.status_code, 201)
        order_number = order_response.json()["order_number"]
        self.login_admin()

        detail = self.client.get(f"/api/admin/orders/{order_number}")
        overview = self.client.get("/api/admin/overview?period=daily")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["tax"], 256)
        self.assertEqual(len(detail.json()["items"]), 1)
        self.assertEqual(overview.json()["kpis"]["revenue"], 0)
        self.assertEqual(overview.json()["kpis"]["average_order_value"], 0)
        self.assertEqual(len(overview.json()["chart"]), 7)

        processing = self.client.patch(
            f"/api/admin/orders/{order_number}/status",
            json={"status": "processing"},
            headers=self.admin_write_headers,
        )
        cancelled = self.client.patch(
            f"/api/admin/orders/{order_number}/status",
            json={"status": "cancelled"},
            headers=self.admin_write_headers,
        )
        cancelled_overview = self.client.get("/api/admin/overview")

        self.assertEqual(processing.status_code, 200)
        self.assertEqual(processing.json()["status"], "processing")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled_overview.json()["kpis"]["revenue"], 0)
        self.assertEqual(cancelled_overview.json()["kpis"]["average_order_value"], 0)
        self.assertEqual(cancelled_overview.json()["top_products"], [])

    def test_admin_campaign_expiry_and_storefront_settings(self) -> None:
        self.login_admin()
        campaign = self.client.post(
            "/api/admin/campaigns",
            json={
                "title": "Weekend Beauty Edit",
                "discount_percent": 20,
                "stock_allocation": 50,
                "duration_minutes": 60,
            },
            headers=self.admin_write_headers,
        )
        self.assertEqual(campaign.status_code, 201, campaign.text)
        self.assertEqual(campaign.json()["active"], 1)

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE campaigns SET ends_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", campaign.json()["id"]),
            )
            connection.commit()
        campaigns = self.client.get("/api/admin/campaigns")
        self.assertEqual(campaigns.json()[0]["active"], 0)

        updated_settings = self.client.put(
            "/api/admin/settings",
            json={"store_status": "maintenance"},
            headers=self.admin_write_headers,
        )
        public_status = self.client.get("/api/admin/storefront/status")
        self.assertEqual(updated_settings.status_code, 200)
        self.assertEqual(public_status.json(), {"store_status": "maintenance"})

    def test_admin_sessions_rbac_and_revocation_are_enforced(self) -> None:
        self.login_admin()
        session = self.client.get("/api/admin/session").json()
        active_sessions = self.client.get("/api/admin/security/sessions")
        role_matrix = self.client.get("/api/admin/security/roles")

        self.assertEqual(session["role"], "Super Admin")
        self.assertTrue(session["session_id"])
        self.assertEqual(len(active_sessions.json()), 1)
        self.assertEqual(active_sessions.json()[0]["session_id"], session["session_id"])
        self.assertEqual(
            {role["role"] for role in role_matrix.json()},
            {"Super Admin", "Store Manager", "Support Agent", "Inventory Clerk"},
        )

        revoked = self.client.delete(
            f"/api/admin/security/sessions/{session['session_id']}",
            headers=self.admin_write_headers,
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(self.client.get("/api/admin/session").json()["authenticated"])
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 401)

    def test_admin_rbac_blocks_disallowed_reads_and_writes(self) -> None:
        with patch.dict(os.environ, {"ADMIN_ROLE": "Support Agent"}):
            self.login_admin()
            session = self.client.get("/api/admin/session")
            allowed_orders = self.client.get("/api/admin/orders")
            denied_analytics = self.client.get("/api/admin/overview")
            denied_settings = self.client.put(
                "/api/admin/settings",
                json={"store_status": "maintenance"},
                headers=self.admin_write_headers,
            )

        self.assertEqual(session.json()["role"], "Support Agent")
        self.assertEqual(allowed_orders.status_code, 200)
        self.assertEqual(denied_analytics.status_code, 403)
        self.assertEqual(denied_settings.status_code, 403)

    def test_analytics_role_without_order_access_does_not_receive_customer_details(self) -> None:
        order = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Private Customer",
                    "phone": "+254700000000",
                    "address": "Private Address",
                },
                "items": [{"product_id": "perf-01", "quantity": 1}],
            },
        )
        self.assertEqual(order.status_code, 201, order.text)
        self.login_admin()
        permissions = {
            "products": {"read": True, "write": False, "delete": False},
            "orders": {"read": False, "write": False, "delete": False},
            "analytics": {"read": True, "write": False, "delete": False},
            "settings": {"read": False, "write": False, "delete": False},
        }
        updated_role = self.client.put(
            "/api/admin/security/roles/Support Agent",
            json={"permissions": permissions},
            headers=self.admin_write_headers,
        )
        self.assertEqual(updated_role.status_code, 200, updated_role.text)
        self.client.post("/api/admin/logout")

        with patch.dict(os.environ, {"ADMIN_ROLE": "Support Agent"}):
            self.login_admin()
            overview = self.client.get("/api/admin/overview")
            denied_orders = self.client.get("/api/admin/orders")

        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(overview.json()["recent_orders"], [])
        self.assertNotIn("Private Customer", overview.text)
        self.assertNotIn("+254700000000", overview.text)
        self.assertEqual(denied_orders.status_code, 403)

    def test_admin_audit_export_filter_and_database_immutability(self) -> None:
        failed_login = self.client.post(
            "/api/admin/login",
            json={"username": "store-admin", "password": "bad-password"},
        )
        self.assertEqual(failed_login.status_code, 401)
        self.login_admin()
        stock_update = self.client.patch(
            "/api/admin/products/perf-01/stock?stock=20",
            headers=self.admin_write_headers,
        )
        self.assertEqual(stock_update.status_code, 200, stock_update.text)

        auth_logs = self.client.get(
            "/api/admin/audit-logs",
            params={"category": "Auth", "search": "login"},
        )
        inventory_logs = self.client.get(
            "/api/admin/audit-logs", params={"category": "Inventory"}
        )
        csv_export = self.client.get(
            "/api/admin/audit-logs", params={"export": "csv"}
        )
        json_export = self.client.get(
            "/api/admin/audit-logs", params={"export": "json"}
        )

        self.assertEqual(auth_logs.status_code, 200)
        self.assertTrue(any("LOGIN_FAILED" in row["event_type"] for row in auth_logs.json()))
        self.assertTrue(any(row["event_type"] == "STOCK_UPDATED" for row in inventory_logs.json()))
        self.assertEqual(csv_export.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("event_category", csv_export.text)
        self.assertEqual(json_export.headers["content-type"], "application/json")
        self.assertIsInstance(json_export.json(), list)

        with closing(sqlite3.connect(self.database_path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE admin_audit_logs SET description = 'tampered' WHERE id = 1"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM admin_audit_logs WHERE id = 1")

    def test_pesapal_payment_logs_and_reconciliation_verify_with_provider(self) -> None:
        order_response = self.client.post(
            "/api/orders",
            json={
                "customer": {
                    "name": "Jamie Rivers",
                    "phone": "+1 555 123 4567",
                    "address": "18 Garden Lane, Portland",
                },
                "items": [{"product_id": "perf-03", "quantity": 1}],
            },
        )
        self.login_admin()
        order_number = order_response.json()["order_number"]
        payments = self.client.get("/api/admin/payments")
        insights = self.client.get("/api/admin/customer-insights")
        with patch("app.pesapal.get_access_token", return_value="provider-token"), patch(
            "app.pesapal._request_json",
            return_value={
                "amount": 3706,
                "currency": "KES",
                "merchant_reference": order_number,
                "payment_status_description": "Completed",
                "confirmation_code": "PESAPAL-RECEIPT",
            },
        ):
            reconcile = self.client.post(
                f"/api/admin/payments/{order_number}/reconcile",
                headers=self.admin_write_headers,
            )

        self.assertTrue(payments.json()["gateway_configured"])
        self.assertEqual(
            payments.json()["transactions"][0]["gateway_reference"],
            order_number,
        )
        self.assertEqual(
            payments.json()["transactions"][0]["gateway_status"],
            "pending_callback",
        )
        self.assertFalse(insights.json()["cart_capture_enabled"])
        self.assertEqual(insights.json()["abandoned_carts"], [])
        self.assertEqual(reconcile.status_code, 200, reconcile.text)
        self.assertEqual(reconcile.json()["payment_status"], "paid")
        self.assertEqual(reconcile.json()["provider_status"], "Completed")

        with closing(sqlite3.connect(self.database_path)) as connection:
            saved_payment = connection.execute(
                "SELECT payment_status, gateway_reference FROM orders WHERE order_number = ?",
                (order_number,),
            ).fetchone()
        self.assertEqual(saved_payment, ("paid", "PESAPAL-RECEIPT"))

    def test_legacy_order_migration_preserves_order_item_foreign_keys(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    delivery_address TEXT NOT NULL,
                    payment_method TEXT NOT NULL
                        CHECK (payment_method IN ('mobile-money', 'card')),
                    status TEXT NOT NULL,
                    payment_status TEXT NOT NULL,
                    subtotal_cents INTEGER NOT NULL,
                    shipping_cents INTEGER NOT NULL,
                    tax_cents INTEGER NOT NULL,
                    total_cents INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    product_id TEXT NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL,
                    unit_price_cents INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    variant TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO orders VALUES (
                    1, 'MM-LEGACY', 'Jamie Rivers', '+1 555 123 4567',
                    '18 Garden Lane', 'card', 'pending', 'pending',
                    320000, 25000, 25600, 370600, '2026-01-01T00:00:00Z'
                );
                """
            )
            connection.commit()

        with patch.dict(os.environ, {"DATABASE_PATH": str(legacy_path)}):
            initialize_database()
            initialize_database()

        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            order = connection.execute(
                """
                SELECT order_number, payment_method, tracking_id, updated_at
                FROM orders WHERE id = 1
                """
            ).fetchone()
            item_foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(order_items)"
            ).fetchall()
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            connection.execute(
                """
                INSERT INTO orders (
                    order_number, customer_name, customer_phone, delivery_address,
                    payment_method, status, payment_status, subtotal_cents,
                    shipping_cents, tax_cents, total_cents
                ) VALUES (
                    'MM-PESAPAL', 'Jamie Rivers', '+1 555 123 4567',
                    '18 Garden Lane', 'pesapal', 'pending', 'pending_callback',
                    100, 0, 0, 100
                )
                """
            )
            connection.execute(
                """
                INSERT INTO orders (
                    order_number, customer_name, customer_phone, delivery_address,
                    payment_method, status, payment_status, subtotal_cents,
                    shipping_cents, tax_cents, total_cents
                ) VALUES (
                    'MM-PESAPAL-2', 'Jamie Rivers', '+1 555 123 4567',
                    '18 Garden Lane', 'pesapal', 'pending', 'pending_callback',
                    100, 0, 0, 100
                )
                """
            )

        self.assertEqual(
            order,
            ("MM-LEGACY", "card", "MM-LEGACY", "2026-01-01T00:00:00Z"),
        )
        self.assertEqual(
            {foreign_key[2] for foreign_key in item_foreign_keys},
            {"orders", "products"},
        )
        self.assertEqual(foreign_key_errors, [])

    def test_existing_users_migrate_without_breaking_seller_references(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy-users.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('buyer', 'seller')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE sellers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    store_name TEXT NOT NULL,
                    store_slug TEXT NOT NULL UNIQUE,
                    logo_url TEXT NOT NULL DEFAULT '',
                    banner_url TEXT NOT NULL DEFAULT '',
                    business_phone TEXT NOT NULL,
                    payout_method TEXT NOT NULL CHECK (payout_method IN ('M-Pesa', 'Bank')),
                    payout_account TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'APPROVED', 'SUSPENDED')),
                    rating REAL NOT NULL DEFAULT 0,
                    commission_percentage REAL NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL
                );
                INSERT INTO users VALUES (1, 'legacy-seller@example.com', 'legacy-hash', 'seller', '2025-01-01');
                INSERT INTO sellers (
                    id, user_id, store_name, store_slug, business_phone,
                    payout_method, payout_account, created_at
                ) VALUES (
                    7, 1, 'Legacy Store', 'legacy-store', '+254700000000',
                    'M-Pesa', '254700000000', '2025-01-01'
                );
                """
            )
            connection.commit()

        with patch.dict(os.environ, {"DATABASE_PATH": str(legacy_path)}):
            initialize_database()
            initialize_database()

        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            user = connection.execute(
                "SELECT id, email, role, full_name, phone FROM users WHERE id = 1"
            ).fetchone()
            profile = connection.execute(
                "SELECT user_id, seller_id, status FROM seller_profiles WHERE seller_id = 7"
            ).fetchone()
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            role_schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()[0]

        self.assertEqual(
            user,
            (1, "legacy-seller@example.com", "seller", "", ""),
        )
        self.assertEqual(profile, (1, 7, "pending"))
        self.assertEqual(foreign_key_errors, [])
        self.assertIn("'admin'", role_schema)

    def test_supplier_cogs_and_low_stock_purchase_orders(self) -> None:
        self.login_admin()
        initial = self.client.get("/api/admin/suppliers/overview")
        updated_cost = self.client.patch(
            "/api/admin/products/perf-01/cost",
            json={"unit_cost": 1200},
            headers=self.admin_write_headers,
        )
        stock = self.client.patch(
            "/api/admin/products/perf-01/stock?stock=2",
            headers=self.admin_write_headers,
        )
        draft = self.client.post(
            "/api/admin/suppliers/purchase-orders/draft-low-stock",
            headers=self.admin_write_headers,
        )
        repeated_draft = self.client.post(
            "/api/admin/suppliers/purchase-orders/draft-low-stock",
            headers=self.admin_write_headers,
        )
        overview = self.client.get("/api/admin/suppliers/overview")

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(updated_cost.status_code, 200)
        self.assertEqual(stock.status_code, 200)
        self.assertGreaterEqual(len(draft.json()["created"]), 1)
        self.assertEqual(repeated_draft.json()["created"], [])
        self.assertEqual(len(overview.json()["purchase_orders"]), len(draft.json()["created"]))
        perfume_margin = next(
            row
            for row in overview.json()["categories"]
            if row["category"] == "Perfumes & Fragrances"
        )
        self.assertIsNotNone(perfume_margin["gross_margin_percent"])


    def test_seller_team_notifications_chat_and_logistics_persist(self) -> None:
        seller = self.register_seller(self.client, "Enterprise Atelier")
        self.login_admin()
        self.approve_seller(seller["id"])
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Enterprise Rose Oil",
                "brand": "Enterprise Atelier",
                "sku": "EA-ROSE-01",
                "category": "Perfumes & Fragrances",
                "detail": "A soft rose fragrance",
                "description": "A carefully blended rose fragrance for everyday wear.",
                "price": 1800,
                "stock": 10,
                "images": ["https://images.example/enterprise-rose.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        product_id = product.json()["id"]
        self.approve_seller_product(product_id)

        invitation = self.client.post(
            "/api/seller/team",
            headers=self.seller_write_headers,
            json={
                "email": "clerk@example.com",
                "full_name": "Inventory Clerk",
                "role": "Inventory Clerk",
            },
        )
        self.assertEqual(invitation.status_code, 201, invitation.text)
        self.assertEqual(invitation.json()["status"], "INVITED")
        self.assertEqual(invitation.json()["delivery_status"], "NOT_SENT")
        self.assertIn("catalog:update_stock", invitation.json()["permissions"])
        self.assertEqual(
            self.client.get("/api/seller/team").json()[0]["email"],
            "clerk@example.com",
        )
        revoked = self.client.patch(
            f"/api/seller/team/{invitation.json()['id']}",
            headers=self.seller_write_headers,
            json={"status": "REVOKED"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)

        preferences = {
            "low_stock_sms": True,
            "low_stock_whatsapp": False,
            "incoming_orders_sms": False,
            "incoming_orders_whatsapp": True,
        }
        saved = self.client.put(
            "/api/seller/notifications",
            headers=self.seller_write_headers,
            json=preferences,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertFalse(saved.json()["delivery_configured"])
        self.assertTrue(
            self.client.get("/api/seller/notifications").json()["low_stock_sms"]
        )

        message = self.client.post(
            "/api/messages",
            json={
                "product_id": product_id,
                "customer_name": "Jamie Buyer",
                "body": "Is this fragrance available in a smaller size?",
            },
        )
        self.assertEqual(message.status_code, 201, message.text)
        conversation_id = message.json()["conversation_id"]
        self.assertEqual(self.client.get("/api/seller/messages").status_code, 200)
        reply = self.client.post(
            "/api/seller/messages/reply",
            headers=self.seller_write_headers,
            json={
                "conversation_id": conversation_id,
                "body": "Yes, a 30 ml option is available.",
            },
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        buyer_thread = self.client.get(f"/api/messages/{conversation_id}")
        self.assertEqual(buyer_thread.status_code, 200, buyer_thread.text)
        self.assertEqual(buyer_thread.json()[-1]["sender_role"], "SELLER")
        buyer_reply = self.client.post(
            f"/api/messages/{conversation_id}",
            json={"body": "Could you also share the delivery estimate?"},
        )
        self.assertEqual(buyer_reply.status_code, 201, buyer_reply.text)
        self.assertEqual(self.client.get("/api/seller/messages").json()[0]["sender_role"], "BUYER")

        mode = self.client.put(
            f"/api/seller/products/{product_id}/fulfillment",
            headers=self.seller_write_headers,
            json={"fulfillment_mode": "MAISON_EXPRESS"},
        )
        self.assertEqual(mode.status_code, 200, mode.text)
        manifest = self.client.post(
            "/api/seller/logistics/manifests",
            headers=self.seller_write_headers,
            json={
                "hub_name": "Nairobi CBD",
                "items": [{"product_id": product_id, "quantity": 2}],
            },
        )
        self.assertEqual(manifest.status_code, 201, manifest.text)
        dropped = self.client.post(
            f"/api/seller/logistics/manifests/{manifest.json()['id']}/dropoff",
            headers=self.seller_write_headers,
            json={},
        )
        self.assertEqual(dropped.status_code, 200, dropped.text)
        with closing(sqlite3.connect(self.database_path)) as connection:
            warehouse_quantity = connection.execute(
                "SELECT quantity FROM seller_warehouse_inventory WHERE product_id = ?",
                (product_id,),
            ).fetchone()[0]
        self.assertEqual(warehouse_quantity, 2)

    def test_seller_qc_vas_branches_repricing_restock_and_statement(self) -> None:
        seller = self.register_seller(self.client, "Studio Seller")
        self.login_admin()
        self.approve_seller(seller["id"])
        product = self.client.post(
            "/api/seller/products",
            headers=self.seller_write_headers,
            json={
                "name": "Studio Rose Oil",
                "brand": "Studio Seller",
                "sku": "SS-ROSE-01",
                "category": "Perfumes & Fragrances",
                "detail": "A soft rose fragrance",
                "description": "A carefully blended rose fragrance for everyday wear.",
                "price": 1800,
                "stock": 10,
                "images": ["https://images.example/studio-rose.jpg"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        product_id = product.json()["id"]
        self.assertEqual(product.json()["status"], "DRAFT")
        self.assertEqual(product.json()["qc_status"], "PENDING_QC")
        self.assertEqual(
            self.client.get("/api/admin/seller-qc").json()[0]["id"],
            product_id,
        )
        cannot_activate = self.client.post(
            "/api/seller/products/bulk",
            headers=self.seller_write_headers,
            json={
                "product_ids": [product_id],
                "action": "status",
                "status": "ACTIVE",
            },
        )
        self.assertEqual(cannot_activate.status_code, 409)

        qc = self.client.post(
            f"/api/admin/seller-qc/{product_id}",
            headers=self.admin_write_headers,
            json={"action": "REJECT", "notes": "Image needs a clean background."},
        )
        self.assertEqual(qc.status_code, 200, qc.text)
        self.assertEqual(qc.json()["qc_status"], "REJECTED_IMAGE_QUALITY")
        resubmitted = self.client.post(
            f"/api/seller/products/{product_id}/qc",
            headers=self.seller_write_headers,
            json={},
        )
        self.assertEqual(resubmitted.status_code, 200, resubmitted.text)
        self.assertEqual(resubmitted.json()["qc_status"], "PENDING_QC")
        vas = self.client.post(
            "/api/seller/vas-requests",
            headers=self.seller_write_headers,
            json={"product_id": product_id, "service_type": "BACKGROUND_CLEANUP"},
        )
        self.assertEqual(vas.status_code, 201, vas.text)
        self.assertEqual(vas.json()["fulfillment_status"], "MANUAL_QUEUE")

        branch = self.client.post(
            "/api/seller/branches",
            headers=self.seller_write_headers,
            json={
                "name": "Westlands Branch",
                "address": "Westlands Mall, Nairobi",
                "city": "Nairobi",
            },
        )
        self.assertEqual(branch.status_code, 201, branch.text)
        allocation = self.client.put(
            f"/api/seller/branches/{branch.json()['id']}/inventory",
            headers=self.seller_write_headers,
            json={"items": [{"product_id": product_id, "quantity": 4}]},
        )
        self.assertEqual(allocation.status_code, 200, allocation.text)
        overallocated = self.client.put(
            f"/api/seller/branches/{branch.json()['id']}/inventory",
            headers=self.seller_write_headers,
            json={"items": [{"product_id": product_id, "quantity": 11}]},
        )
        self.assertEqual(overallocated.status_code, 409)

        repricing = self.client.put(
            f"/api/seller/products/{product_id}/repricing",
            headers=self.seller_write_headers,
            json={
                "min_price": 1000,
                "max_price": 2000,
                "rule": "CLEARANCE_DISCOUNT",
            },
        )
        self.assertEqual(repricing.status_code, 200, repricing.text)
        self.assertEqual(repricing.json()["applied_price"], 1620)
        self.assertEqual(self.client.get("/api/seller/statements/weekly").status_code, 200)
        restock = self.client.post(
            f"/api/seller/products/{product_id}/restock",
            headers=self.seller_write_headers,
            json={"recommended_quantity": 12},
        )
        self.assertEqual(restock.status_code, 201, restock.text)
        self.assertEqual(self.client.get("/api/seller/insights").status_code, 200)

        self.assertNotIn(
            product_id,
            {item["id"] for item in self.client.get("/api/products").json()},
        )
        qc = self.client.post(
            f"/api/admin/seller-qc/{product_id}",
            headers=self.admin_write_headers,
            json={"action": "APPROVE", "notes": "Listing passed QC."},
        )
        self.assertEqual(qc.status_code, 200, qc.text)
        self.assertIn(
            product_id,
            {item["id"] for item in self.client.get("/api/products").json()},
        )
        public_store = self.client.get(f"/api/sellers/{seller['store_slug']}")
        self.assertEqual(public_store.status_code, 200, public_store.text)
        self.assertIn(
            product_id,
            {item["id"] for item in public_store.json()["products"]},
        )
        category_products = self.client.get(
            "/api/products?category=beauty-cosmetics"
        )
        self.assertEqual(category_products.status_code, 200, category_products.text)
        self.assertIn(product_id, {item["id"] for item in category_products.json()})
        channel_products = self.client.get(
            "/api/products?category=electronics,beauty-cosmetics"
        )
        self.assertEqual(channel_products.status_code, 200, channel_products.text)
        self.assertIn(product_id, {item["id"] for item in channel_products.json()})
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE products SET old_price = price + 100, discount = '10%' WHERE id = ?",
                (product_id,),
            )
            connection.commit()
        deals = self.client.get("/api/products?deals=true")
        self.assertEqual(deals.status_code, 200, deals.text)
        self.assertIn(product_id, {item["id"] for item in deals.json()})

    def test_seller_excel_catalog_import_creates_pending_qc_listings(self) -> None:
        seller = self.register_seller(self.client, "Excel Catalog Studio")
        self.login_admin()
        self.approve_seller(seller["id"])
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(
            [
                "name",
                "brand",
                "sku",
                "category",
                "detail",
                "description",
                "price",
                "stock",
                "images",
            ]
        )
        worksheet.append(
            [
                "Excel Rose Serum",
                "Excel Catalog Studio",
                "EXCEL-SERUM-01",
                "Skincare & Glow",
                "A light daily serum",
                "A gentle serum for a hydrated daily skincare routine.",
                1200,
                15,
                "https://images.example/excel-serum.jpg",
            ]
        )
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        imported = self.client.post(
            "/api/products/bulk-upload",
            headers=self.seller_write_headers,
            files={
                "file": (
                    "catalog.xlsx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["created"], 1)
        pending = self.client.get("/api/seller/qc").json()
        self.assertEqual(pending[0]["qc_status"], "PENDING_QC")
        self.assertEqual(pending[0]["product_status"], "DRAFT")

    def test_support_bot_replies_to_keywords_while_waiting_for_agent(self) -> None:
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as guest_client:
            bot_response = guest_client.post(
                "/api/support/message",
                json={"message": "How do I sell here?"},
            )
            self.assertEqual(bot_response.status_code, 200, bot_response.text)
            self.assertEqual(bot_response.json()["status"], "BOT")
            self.assertEqual(
                sum(
                    message["sender_type"] == "BOT"
                    for message in bot_response.json()["messages"]
                ),
                1,
            )
            self.assertIn(
                "seller registration",
                bot_response.json()["bot_reply"]["message"],
            )

            handoff = guest_client.post(
                "/api/support/message",
                json={"message": "Talk to an agent", "intent": "human"},
            )
            self.assertEqual(handoff.status_code, 200, handoff.text)
            ticket = handoff.json()
            self.assertEqual(ticket["status"], "WAITING_AGENT")
            self.assertIn("connecting", ticket["bot_reply"]["message"].lower())

            headers = {"X-Support-Token": ticket["access_token"]}
            bot_count = 1
            for message, expected in (
                ("How do I register my store to sell?", "seller registration"),
                ("I need help with M-Pesa checkout", "All storefront purchases"),
                ("Where is my delivery?", "Tracking ID"),
                ("What are the monthly fees and commission?", "KSh 2,500/month"),
                ("Can I list a cow on WhatsApp?", "For Farmers & Livestock Sellers"),
                ("How do I withdraw escrow to my Paybill?", "instant B2C withdrawals"),
                ("Can I track through Fargo?", "Order Tracking page"),
                ("Is this seller real and verified?", "Every seller on Maison Muse"),
            ):
                with self.subTest(message=message):
                    reply = guest_client.post(
                        "/api/support/message",
                        headers=headers,
                        json={"ticket_id": ticket["ticket_id"], "message": message},
                    )
                    self.assertEqual(reply.status_code, 200, reply.text)
                    result = reply.json()
                    self.assertEqual(result["status"], "WAITING_AGENT")
                    self.assertEqual(result["bot_reply"]["sender_type"], "BOT")
                    self.assertIn(expected, result["bot_reply"]["message"])
                    bot_count += 1
                    self.assertEqual(
                        sum(
                            item["sender_type"] == "BOT"
                            for item in result["messages"]
                        ),
                        bot_count,
                    )

            fallback = guest_client.post(
                "/api/support/message",
                headers=headers,
                json={
                    "ticket_id": ticket["ticket_id"],
                    "message": "Can you help with something unusual?",
                },
            )
            self.assertEqual(fallback.status_code, 200, fallback.text)
            self.assertEqual(
                fallback.json()["bot_reply"]["suggested_actions"],
                [
                    {"intent": "seller_plans", "label": "Ask about Seller Plans"},
                    {"intent": "mpesa_help", "label": "Ask about M-Pesa"},
                    {"intent": "human", "label": "Connect with Live Admin"},
                ],
            )

            restored = guest_client.get(
                f"/api/support/tickets/{ticket['ticket_id']}", headers=headers
            )
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(
                sum(message["sender_type"] == "BOT" for message in restored.json()["messages"]),
                bot_count + 1,
            )

    def test_support_bot_handles_order_actions_and_redacts_sensitive_chat_content(self) -> None:
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as guest_client:
            cancelled = guest_client.post(
                "/api/support/message",
                json={
                    "message": "MM-DEMO-95A1E6C333A5FA77 I want cancel my order",
                },
            )
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["status"], "BOT")
            self.assertIn(
                "sign in to your buyer account",
                cancelled.json()["bot_reply"]["message"],
            )

            refund = guest_client.post(
                "/api/support/message",
                json={"message": "I want a refund for my order"},
            )
            self.assertEqual(refund.status_code, 200, refund.text)
            self.assertEqual(refund.json()["status"], "WAITING_AGENT")
            self.assertIn(
                "can’t approve or issue",
                refund.json()["bot_reply"]["message"],
            )

            secret = "My password is hunter2 and my OTP is 123456"
            privacy = guest_client.post(
                "/api/support/message",
                json={"message": secret},
            )
            self.assertEqual(privacy.status_code, 200, privacy.text)
            self.assertIn("passwords", privacy.json()["bot_reply"]["message"])
            self.assertIn(
                "[Message hidden for safety",
                privacy.json()["messages"][-2]["message"],
            )
            self.assertNotIn(secret, privacy.text)

            contact = "+254712345678"
            redacted = guest_client.post(
                "/api/support/message",
                json={"message": f"My phone number is {contact}; M-Pesa checkout failed."},
            )
            self.assertEqual(redacted.status_code, 200, redacted.text)
            self.assertNotIn(contact, redacted.text)
            self.assertIn(
                "[contact details removed]",
                redacted.json()["messages"][-2]["message"],
            )

    def test_support_bot_cancels_only_confirmed_failed_unfulfilled_buyer_orders(self) -> None:
        registration = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Order Cancellation Buyer",
                "email": "cancellation-buyer@example.com",
                "password": "a-very-secure-password",
                "role": "buyer",
                "phone": "+254700000001",
            },
        )
        self.assertEqual(registration.status_code, 201, registration.text)
        buyer_headers = {
            "Authorization": f"Bearer {registration.json()['access_token']}"
        }
        order_response = self.client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "customer": {
                    "name": "Order Cancellation Buyer",
                    "phone": "+254700000001",
                    "address": "1 Buyer Road",
                },
                "items": [{"product_id": "perf-01", "quantity": 1}],
            },
        )
        self.assertEqual(order_response.status_code, 201, order_response.text)
        order_number = order_response.json()["order_number"]
        seller = self.register_seller(self.client, "Cancellation Test Boutique")
        with closing(sqlite3.connect(self.database_path)) as connection:
            order_id = connection.execute(
                "SELECT id FROM orders WHERE order_number = ?", (order_number,)
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO sub_orders (
                    parent_order_id, seller_id, items_json, subtotal,
                    commission_amount, seller_payout_amount
                ) VALUES (?, ?, '[]', 100, 10, 90)
                """,
                (order_id, seller["id"]),
            )
            connection.execute(
                "UPDATE orders SET payment_status = 'failed' WHERE order_number = ?",
                (order_number,),
            )
            connection.commit()
            cancellation_state = connection.execute(
                """
                SELECT o.status, o.payment_status, so.fulfillment_status,
                       so.admin_override_status
                FROM orders o JOIN sub_orders so ON so.parent_order_id = o.id
                WHERE o.order_number = ?
                """,
                (order_number,),
            ).fetchone()
        self.assertEqual(
            tuple(cancellation_state), ("pending", "failed", "PENDING", "")
        )
        other_buyer = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Different Buyer",
                "email": "different-buyer@example.com",
                "password": "another-secure-password",
                "role": "buyer",
                "phone": "+254700000002",
            },
        )
        self.assertEqual(other_buyer.status_code, 201, other_buyer.text)
        unauthorized = self.client.post(
            "/api/support/message",
            headers={
                "Authorization": f"Bearer {other_buyer.json()['access_token']}"
            },
            json={
                "intent": "order_cancel",
                "message": f"Cancel order {order_number}",
            },
        )
        self.assertEqual(unauthorized.status_code, 200, unauthorized.text)
        self.assertIn(
            "couldn’t verify",
            unauthorized.json()["bot_reply"]["message"],
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            order_status_after_unauthorized_request = connection.execute(
                "SELECT status FROM orders WHERE order_number = ?", (order_number,)
            ).fetchone()[0]
        self.assertEqual(order_status_after_unauthorized_request, "pending")

        request_cancellation = self.client.post(
            "/api/support/message",
            headers=buyer_headers,
            json={
                "intent": "order_cancel",
                "message": "Cancel or change an order",
            },
        )
        self.assertEqual(request_cancellation.status_code, 200, request_cancellation.text)
        self.assertEqual(
            request_cancellation.json()["status"],
            "BOT",
            request_cancellation.json(),
        )
        order_reference = self.client.post(
            "/api/support/message",
            headers=buyer_headers,
            json={
                "ticket_id": request_cancellation.json()["ticket_id"],
                "message": order_number,
            },
        )
        self.assertEqual(order_reference.status_code, 200, order_reference.text)
        self.assertEqual(order_reference.json()["status"], "BOT")
        self.assertIn(
            "nothing will change until you confirm",
            order_reference.json()["bot_reply"]["message"].lower(),
        )
        confirm_action = order_reference.json()["bot_reply"]["suggested_actions"][0]
        self.assertEqual(confirm_action["intent"], "confirm_order_cancel")

        confirmed = self.client.post(
            "/api/support/message",
            headers=buyer_headers,
            json={
                "ticket_id": order_reference.json()["ticket_id"],
                "intent": confirm_action["intent"],
                "message": confirm_action["label"],
            },
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertIn("is cancelled", confirmed.json()["bot_reply"]["message"])
        self.assertEqual(confirmed.json()["status"], "BOT")
        tracking = self.client.get(f"/api/orders/track/{order_number}")
        self.assertEqual(tracking.status_code, 200, tracking.text)
        self.assertEqual(tracking.json()["status"], "CANCELLED")
        with closing(sqlite3.connect(self.database_path)) as connection:
            order_status = connection.execute(
                "SELECT status FROM orders WHERE order_number = ?", (order_number,)
            ).fetchone()[0]
            events = connection.execute(
                """
                SELECT status, actor FROM order_status_events
                WHERE parent_order_id = (
                    SELECT id FROM orders WHERE order_number = ?
                )
                ORDER BY id DESC
                """,
                (order_number,),
            ).fetchall()
        self.assertEqual(order_status, "cancelled")
        self.assertEqual(tuple(events[0]), ("CANCELLED", "buyer_support_bot"))

        pending_order = self.client.post(
            "/api/orders",
            headers=buyer_headers,
            json={
                "customer": {
                    "name": "Order Cancellation Buyer",
                    "phone": "+254700000001",
                    "address": "1 Buyer Road",
                },
                "items": [{"product_id": "perf-01", "quantity": 1}],
            },
        )
        self.assertEqual(pending_order.status_code, 201, pending_order.text)
        pending_number = pending_order.json()["order_number"]
        blocked = self.client.post(
            "/api/support/message",
            headers=buyer_headers,
            json={
                "intent": "order_cancel",
                "message": f"Please cancel order {pending_number}",
            },
        )
        self.assertEqual(blocked.status_code, 200, blocked.text)
        self.assertEqual(blocked.json()["status"], "WAITING_AGENT")
        self.assertIn("no cancellation or refund was applied", blocked.json()["bot_reply"]["message"].lower())
        with closing(sqlite3.connect(self.database_path)) as connection:
            unchanged_status = connection.execute(
                "SELECT status FROM orders WHERE order_number = ?", (pending_number,)
            ).fetchone()[0]
        self.assertEqual(unchanged_status, "pending")

    def test_customer_support_handoff_admin_reply_and_websocket_delivery(self) -> None:
        from fastapi.testclient import TestClient

        preflight = self.client.options(
            "/api/support/message",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-support-token",
            },
        )
        self.assertEqual(preflight.status_code, 200, preflight.text)
        self.assertEqual(
            preflight.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

        with TestClient(create_app()) as guest_client:
            created = guest_client.post(
                "/api/support/message",
                json={
                    "message": "Talk to a Live Support Agent",
                    "intent": "human",
                    "customer_name": "Casey Buyer",
                    "customer_email": "casey@example.com",
                    "cart_items": [{"name": "Rose Serum", "quantity": 2}],
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            ticket = created.json()
            self.assertEqual(ticket["status"], "WAITING_AGENT")
            self.assertTrue(ticket["access_token"])
            self.assertTrue(
                any(
                    message["sender_type"] == "BOT"
                    and "connecting" in message["message"].lower()
                    for message in ticket["messages"]
                )
            )

            ticket_id = ticket["ticket_id"]
            token_header = {"X-Support-Token": ticket["access_token"]}
            restored = guest_client.get(
                f"/api/support/tickets/{ticket_id}", headers=token_header
            )
            self.assertEqual(restored.status_code, 200, restored.text)
            denied = guest_client.get(
                f"/api/support/tickets/{ticket_id}",
                headers={"X-Support-Token": "not-the-ticket-token"},
            )
            self.assertEqual(denied.status_code, 403)

            self.login_admin()
            admin_tickets = self.client.get("/api/admin/support/tickets")
            self.assertEqual(admin_tickets.status_code, 200, admin_tickets.text)
            support_ticket = next(
                item for item in admin_tickets.json() if item["id"] == ticket_id
            )
            self.assertEqual(support_ticket["customer"]["name"], "Casey Buyer")
            self.assertEqual(
                support_ticket["cart_items"],
                [{"name": "Rose Serum", "quantity": 2}],
            )
            details = self.client.get(f"/api/admin/support/tickets/{ticket_id}")
            self.assertEqual(details.status_code, 200, details.text)
            self.assertEqual(len(details.json()["messages"]), len(ticket["messages"]))

            with self.client.websocket_connect(f"/ws/support/{ticket_id}") as admin_socket:
                presence = admin_socket.receive_json()
                self.assertEqual(presence["type"], "presence")
                self.assertEqual(presence["agents_online"], 1)

            with guest_client.websocket_connect(f"/ws/support/{ticket_id}") as socket:
                guest_reply = guest_client.post(
                    "/api/support/message",
                    headers=token_header,
                    json={"ticket_id": ticket_id, "message": "Please check my order."},
                )
                self.assertEqual(guest_reply.status_code, 200, guest_reply.text)
                event = socket.receive_json()
                self.assertEqual(event["type"], "message")
                self.assertEqual(event["message"]["sender_type"], "USER")
                self.assertEqual(event["message"]["message"], "Please check my order.")

            replied = self.client.post(
                "/api/admin/support/reply",
                headers=self.admin_write_headers,
                json={"ticket_id": ticket_id, "message": "I can help with that."},
            )
            self.assertEqual(replied.status_code, 201, replied.text)

            refreshed = guest_client.get(
                f"/api/support/tickets/{ticket_id}", headers=token_header
            )
            self.assertEqual(refreshed.json()["status"], "WAITING_AGENT")
            self.assertTrue(
                any(message["sender_type"] == "ADMIN" for message in refreshed.json()["messages"])
            )


if __name__ == "__main__":
    unittest.main()
