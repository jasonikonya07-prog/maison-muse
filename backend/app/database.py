import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import get_database_path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('buyer', 'seller', 'admin')),
                phone TEXT NOT NULL DEFAULT '',
                business_type TEXT NOT NULL DEFAULT '',
                whatsapp_number TEXT NOT NULL DEFAULT '',
                google_subject TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS sellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                store_name TEXT NOT NULL,
                store_bio TEXT NOT NULL DEFAULT '',
                store_slug TEXT NOT NULL UNIQUE,
                logo_url TEXT NOT NULL DEFAULT '',
                banner_url TEXT NOT NULL DEFAULT '',
                business_phone TEXT NOT NULL,
                payout_method TEXT NOT NULL CHECK (payout_method IN ('M-Pesa', 'Bank')),
                payout_account TEXT NOT NULL,
                business_category TEXT NOT NULL DEFAULT '',
                business_type TEXT NOT NULL DEFAULT '',
                whatsapp_phone TEXT NOT NULL DEFAULT '',
                whatsapp_number TEXT NOT NULL DEFAULT '',
                instagram_url TEXT NOT NULL DEFAULT '',
                tiktok_url TEXT NOT NULL DEFAULT '',
                operating_hours TEXT NOT NULL DEFAULT '',
                holiday_mode INTEGER NOT NULL DEFAULT 0 CHECK (holiday_mode IN (0, 1)),
                city TEXT NOT NULL DEFAULT '',
                business_registration_number TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'APPROVED', 'SUSPENDED')),
                owner_name TEXT NOT NULL DEFAULT '',
                submitted_documents_json TEXT NOT NULL DEFAULT '[]',
                review_note TEXT NOT NULL DEFAULT '',
                review_state TEXT NOT NULL DEFAULT 'CLEAR'
                    CHECK (review_state IN ('CLEAR', 'UNDER_AUDIT')),
                commission_is_custom INTEGER NOT NULL DEFAULT 0
                    CHECK (commission_is_custom IN (0, 1)),
                rating REAL NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
                commission_percentage REAL NOT NULL DEFAULT 10
                    CHECK (commission_percentage BETWEEN 0 AND 100),
                accepted_terms INTEGER NOT NULL DEFAULT 0
                    CHECK (accepted_terms IN (0, 1)),
                selected_plan TEXT
                    CHECK (selected_plan IS NULL OR selected_plan IN ('boutique', 'pro', 'enterprise')),
                commission_rate REAL NOT NULL DEFAULT 10
                    CHECK (commission_rate BETWEEN 0 AND 100),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                seller_id INTEGER NOT NULL UNIQUE REFERENCES sellers(id) ON DELETE CASCADE,
                store_name TEXT NOT NULL,
                store_slug TEXT NOT NULL UNIQUE,
                business_phone TEXT NOT NULL,
                payout_number TEXT NOT NULL,
                business_category TEXT NOT NULL DEFAULT '',
                business_registration_number TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved'))
            );

            CREATE TABLE IF NOT EXISTS seller_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS seller_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1)),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_seller_login_attempts_time
                ON seller_login_attempts(created_at, ip_address);

            CREATE TABLE IF NOT EXISTS user_login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_user_login_events_user_time
                ON user_login_events(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS seller_complaint_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                admin_username TEXT NOT NULL,
                complaint_summary TEXT NOT NULL,
                complaint_reference TEXT NOT NULL DEFAULT '',
                delivery_status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_seller_complaint_warnings_seller_time
                ON seller_complaint_warnings(seller_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT 'Maison Muse',
                sku TEXT UNIQUE,
                category TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                price REAL NOT NULL CHECK (price >= 0),
                old_price REAL,
                discount TEXT NOT NULL DEFAULT '',
                rating REAL CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
                reviews_count INTEGER NOT NULL DEFAULT 0 CHECK (reviews_count >= 0),
                tag TEXT NOT NULL DEFAULT 'JUST FOR YOU',
                tag_color TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                low_stock_threshold INTEGER NOT NULL DEFAULT 5 CHECK (low_stock_threshold >= 0),
                image TEXT NOT NULL,
                gallery_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                variants_json TEXT NOT NULL DEFAULT '[]',
                product_status TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (product_status IN ('ACTIVE', 'DRAFT', 'ARCHIVED')),
                notes_json TEXT NOT NULL DEFAULT '[]',
                nail_sizes_json TEXT NOT NULL DEFAULT '[]',
                highlights_json TEXT NOT NULL DEFAULT '[]',
                details_json TEXT NOT NULL DEFAULT '{}',
                tone TEXT NOT NULL DEFAULT 'rose',
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                is_agri_product INTEGER NOT NULL DEFAULT 0 CHECK (is_agri_product IN (0, 1)),
                farmer_name TEXT NOT NULL DEFAULT '',
                farmer_whatsapp TEXT NOT NULL DEFAULT '',
                seller_whatsapp_phone TEXT NOT NULL DEFAULT '',
                seller_id INTEGER REFERENCES sellers(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
                icon_name TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS seller_profile_update_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                new_email TEXT NOT NULL,
                new_phone TEXT NOT NULL,
                code_salt TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_profile_update_pending
                ON seller_profile_update_tokens(seller_id, used_at, expires_at);

            CREATE TABLE IF NOT EXISTS seller_subscription_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                selected_plan TEXT NOT NULL CHECK (selected_plan IN ('boutique', 'pro', 'enterprise')),
                amount REAL NOT NULL CHECK (amount >= 0),
                payment_method TEXT NOT NULL DEFAULT 'M-Pesa STK (SIMULATED)',
                reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'COMPLETED'
                    CHECK (status IN ('COMPLETED', 'FAILED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
                product_ids_json TEXT NOT NULL DEFAULT '[]',
                promotion_type TEXT NOT NULL
                    CHECK (promotion_type IN ('flash_sale', 'coupon', 'price_discount')),
                name TEXT NOT NULL,
                code TEXT,
                discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 90),
                usage_limit INTEGER NOT NULL DEFAULT 0 CHECK (usage_limit >= 0),
                usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0),
                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE', 'PAUSED', 'EXPIRED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(seller_id, code)
            );
            CREATE INDEX IF NOT EXISTS idx_seller_promotions_active
                ON seller_promotions(seller_id, status, expires_at);

            CREATE TABLE IF NOT EXISTS seller_campaign_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_ids_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE', 'WITHDRAWN')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(campaign_id, seller_id)
            );
            CREATE INDEX IF NOT EXISTS idx_seller_campaign_enrollments_seller
                ON seller_campaign_enrollments(seller_id, status);

            CREATE TABLE IF NOT EXISTS seller_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                sub_order_id INTEGER NOT NULL REFERENCES sub_orders(id) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'REFUND_APPROVED', 'REPLACEMENT_OFFERED', 'ESCALATED', 'CLOSED')),
                evidence TEXT NOT NULL DEFAULT '',
                resolution_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_returns_status
                ON seller_returns(seller_id, status, created_at DESC);

            CREATE TABLE IF NOT EXISTS seller_ad_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                amount REAL NOT NULL CHECK (amount >= 0),
                duration_days INTEGER NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
                reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'COMPLETED'
                    CHECK (status IN ('COMPLETED', 'FAILED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                email TEXT NOT NULL COLLATE NOCASE,
                full_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL CHECK (
                    role IN ('Inventory Clerk', 'Fulfillment Manager', 'Accountant')
                ),
                permissions_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'INVITED'
                    CHECK (status IN ('INVITED', 'ACTIVE', 'REVOKED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(seller_id, email)
            );
            CREATE INDEX IF NOT EXISTS idx_seller_team_members_seller
                ON seller_team_members(seller_id, status);

            CREATE TABLE IF NOT EXISTS seller_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
                sender_role TEXT NOT NULL CHECK (sender_role IN ('BUYER', 'SELLER')),
                sender_name TEXT NOT NULL,
                body TEXT NOT NULL,
                read_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_messages_conversation
                ON seller_messages(seller_id, conversation_id, id);

            CREATE TABLE IF NOT EXISTS seller_notification_preferences (
                seller_id INTEGER PRIMARY KEY REFERENCES sellers(id) ON DELETE CASCADE,
                low_stock_sms INTEGER NOT NULL DEFAULT 0 CHECK (low_stock_sms IN (0, 1)),
                low_stock_whatsapp INTEGER NOT NULL DEFAULT 0 CHECK (low_stock_whatsapp IN (0, 1)),
                incoming_orders_sms INTEGER NOT NULL DEFAULT 0 CHECK (incoming_orders_sms IN (0, 1)),
                incoming_orders_whatsapp INTEGER NOT NULL DEFAULT 0 CHECK (incoming_orders_whatsapp IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_warehouse_inventory (
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY (seller_id, product_id)
            );

            CREATE TABLE IF NOT EXISTS seller_dropoff_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                hub_name TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'READY'
                    CHECK (status IN ('READY', 'DROPPED_OFF', 'CANCELLED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS seller_dropoff_manifest_items (
                manifest_id INTEGER NOT NULL REFERENCES seller_dropoff_manifests(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                PRIMARY KEY (manifest_id, product_id)
            );

            CREATE TABLE IF NOT EXISTS seller_qc_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                qc_status TEXT NOT NULL CHECK (
                    qc_status IN ('PENDING_QC', 'APPROVED_LIVE', 'REJECTED_IMAGE_QUALITY')
                ),
                notes TEXT NOT NULL DEFAULT '',
                reviewed_by TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_qc_audits_product
                ON seller_qc_audits(seller_id, product_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS seller_vas_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                service_type TEXT NOT NULL CHECK (
                    service_type IN ('BACKGROUND_CLEANUP', 'SEO_ENHANCEMENT')
                ),
                status TEXT NOT NULL DEFAULT 'REQUESTED'
                    CHECK (status IN ('REQUESTED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_financial_statement_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                sub_order_id INTEGER NOT NULL UNIQUE REFERENCES sub_orders(id) ON DELETE CASCADE,
                gross_revenue REAL NOT NULL,
                commission REAL NOT NULL,
                commission_vat REAL NOT NULL,
                shipping_contribution REAL NOT NULL DEFAULT 0,
                net_balance REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS seller_penalty_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                sub_order_id INTEGER REFERENCES sub_orders(id) ON DELETE SET NULL,
                product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
                reason TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0 CHECK (amount >= 0),
                status TEXT NOT NULL DEFAULT 'AUDIT'
                    CHECK (status IN ('AUDIT', 'WAIVED', 'CHARGED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_repricing_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
                min_price REAL NOT NULL CHECK (min_price > 0),
                max_price REAL NOT NULL CHECK (max_price >= min_price),
                rule TEXT NOT NULL CHECK (
                    rule IN ('CLEARANCE_DISCOUNT', 'MATCH_LOWEST_MARKET_PRICE')
                ),
                applied_price REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(seller_id, name)
            );
            CREATE TABLE IF NOT EXISTS seller_branch_inventory (
                branch_id INTEGER NOT NULL REFERENCES seller_branches(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY (branch_id, product_id)
            );

            CREATE TABLE IF NOT EXISTS seller_restock_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                recommended_quantity INTEGER NOT NULL CHECK (recommended_quantity > 0),
                status TEXT NOT NULL DEFAULT 'REQUESTED'
                    CHECK (status IN ('REQUESTED', 'ORDERED', 'RECEIVED', 'CANCELLED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS seller_review_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                sub_order_id INTEGER NOT NULL REFERENCES sub_orders(id) ON DELETE CASCADE,
                channel TEXT NOT NULL CHECK (channel IN ('EMAIL', 'SMS')),
                destination_hint TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'QUEUED'
                    CHECK (status IN ('QUEUED', 'SENT', 'FAILED', 'SIMULATED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(sub_order_id, channel)
            );

            CREATE INDEX IF NOT EXISTS idx_products_category_name
                ON products(category, name);

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                tracking_id TEXT NOT NULL DEFAULT '',
                buyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                delivery_address TEXT NOT NULL,
                payment_method TEXT NOT NULL
                    CHECK (payment_method IN ('mobile-money', 'card', 'pesapal')),
                payment_gateway TEXT NOT NULL DEFAULT '',
                gateway_reference TEXT NOT NULL DEFAULT '',
                gateway_tracking_id TEXT NOT NULL DEFAULT '',
                gateway_status TEXT NOT NULL DEFAULT '',
                mpesa_phone TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                shipping_cents INTEGER NOT NULL CHECK (shipping_cents >= 0),
                tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
                total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                payment_attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                variant TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS sub_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                seller_id INTEGER NOT NULL REFERENCES sellers(id),
                items_json TEXT NOT NULL DEFAULT '[]',
                subtotal REAL NOT NULL CHECK (subtotal >= 0),
                commission_amount REAL NOT NULL CHECK (commission_amount >= 0),
                seller_payout_amount REAL NOT NULL CHECK (seller_payout_amount >= 0),
                fulfillment_status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (fulfillment_status IN ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED')),
                admin_override_status TEXT NOT NULL DEFAULT '',
                courier_name TEXT NOT NULL DEFAULT '',
                tracking_number TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(parent_order_id, seller_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sub_orders_seller_status
                ON sub_orders(seller_id, fulfillment_status);
            CREATE TABLE IF NOT EXISTS order_status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                sub_order_id INTEGER NOT NULL REFERENCES sub_orders(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_order_status_events_sub_order
                ON order_status_events(sub_order_id, created_at, id);

            CREATE TABLE IF NOT EXISTS seller_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                buyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                sub_order_id INTEGER NOT NULL UNIQUE REFERENCES sub_orders(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL DEFAULT '',
                is_verified INTEGER NOT NULL DEFAULT 1 CHECK (is_verified IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_reviews_public
                ON seller_reviews(seller_id, is_verified, created_at DESC);

            CREATE TABLE IF NOT EXISTS seller_payout_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
                sub_order_id INTEGER NOT NULL UNIQUE REFERENCES sub_orders(id) ON DELETE CASCADE,
                gross_amount REAL NOT NULL CHECK (gross_amount >= 0),
                commission_amount REAL NOT NULL CHECK (commission_amount >= 0),
                net_amount REAL NOT NULL CHECK (net_amount >= 0),
                status TEXT NOT NULL,
                transaction_reference TEXT NOT NULL DEFAULT '',
                payout_reference TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seller_payout_ledger_seller_status
                ON seller_payout_ledger(seller_id, status);

            CREATE TABLE IF NOT EXISTS payout_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL REFERENCES sellers(id),
                amount REAL NOT NULL CHECK (amount > 0),
                commission_retained REAL NOT NULL DEFAULT 0 CHECK (commission_retained >= 0),
                payout_method TEXT NOT NULL CHECK (payout_method IN ('M-Pesa', 'Bank')),
                reference TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'PROCESSING'
                    CHECK (status IN ('COMPLETED', 'FAILED', 'PROCESSING')),
                transaction_id TEXT NOT NULL DEFAULT '',
                failure_reason TEXT NOT NULL DEFAULT '',
                destination_type TEXT NOT NULL DEFAULT 'registered_phone',
                destination_hint TEXT NOT NULL DEFAULT '',
                paid_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS payout_allocations (
                payout_transaction_id INTEGER NOT NULL REFERENCES payout_transactions(id),
                sub_order_id INTEGER NOT NULL UNIQUE REFERENCES sub_orders(id),
                PRIMARY KEY (payout_transaction_id, sub_order_id)
            );
            CREATE TABLE IF NOT EXISTS seller_demo_payout_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payout_transaction_id INTEGER NOT NULL REFERENCES payout_transactions(id),
                ledger_id INTEGER NOT NULL REFERENCES seller_payout_ledger(id),
                amount REAL NOT NULL CHECK (amount > 0),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS marketplace_commission_category_rates (
                seller_id INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL,
                percentage REAL NOT NULL CHECK (percentage BETWEEN 0 AND 100),
                PRIMARY KEY (seller_id, category)
            );
            CREATE TABLE IF NOT EXISTS marketplace_disputes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sub_order_id INTEGER NOT NULL REFERENCES sub_orders(id),
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0 CHECK (amount >= 0),
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_marketplace_disputes_sub_order
                ON marketplace_disputes(sub_order_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                subscribed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS support_tickets (
                id TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                guest_session_id TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                customer_email TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',
                cart_snapshot_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'BOT'
                    CHECK (status IN ('BOT', 'WAITING_AGENT', 'RESOLVED')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_support_tickets_status_updated
                ON support_tickets(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_support_tickets_user
                ON support_tickets(user_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
                sender_type TEXT NOT NULL CHECK (sender_type IN ('USER', 'BOT', 'ADMIN')),
                sender_name TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                attachments_json TEXT NOT NULL DEFAULT '[]',
                timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_support_messages_ticket_time
                ON support_messages(ticket_id, timestamp, id);

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 90),
                stock_allocation INTEGER NOT NULL CHECK (stock_allocation >= 0),
                duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 1 AND 10080),
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS store_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_sessions (
                session_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                user_agent TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                succeeded INTEGER NOT NULL CHECK (succeeded IN (0, 1)),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_admin_login_attempts_time
                ON admin_login_attempts(created_at, ip_address);

            CREATE TABLE IF NOT EXISTS admin_role_permissions (
                role TEXT PRIMARY KEY,
                permissions_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                admin_username TEXT NOT NULL,
                event_category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_admin_audit_time
                ON admin_audit_logs(occurred_at DESC);
            CREATE TRIGGER IF NOT EXISTS prevent_admin_audit_update
                BEFORE UPDATE ON admin_audit_logs
                BEGIN
                    SELECT RAISE(ABORT, 'Admin audit logs are immutable.');
                END;
            CREATE TRIGGER IF NOT EXISTS prevent_admin_audit_delete
                BEFORE DELETE ON admin_audit_logs
                BEGIN
                    SELECT RAISE(ABORT, 'Admin audit logs are immutable.');
                END;

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_cost REAL NOT NULL CHECK (unit_cost >= 0),
                total_cost REAL NOT NULL CHECK (total_cost >= 0),
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'submitted', 'received', 'cancelled')),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(users)")
        }
        user_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()["sql"]
        if (
            not {
                "full_name",
                "phone",
                "business_type",
                "whatsapp_number",
                "google_subject",
            }.issubset(user_columns)
            or "'admin'" not in user_table_sql.casefold()
        ):
            connection.commit()
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA legacy_alter_table = ON")
            try:
                connection.execute("BEGIN IMMEDIATE")
                full_name = "full_name" if "full_name" in user_columns else "''"
                phone = "phone" if "phone" in user_columns else "''"
                business_type = (
                    "business_type" if "business_type" in user_columns else "''"
                )
                whatsapp_number = (
                    "whatsapp_number" if "whatsapp_number" in user_columns else "''"
                )
                google_subject = (
                    "google_subject" if "google_subject" in user_columns else "NULL"
                )
                connection.execute(
                    """
                    CREATE TABLE users_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        full_name TEXT NOT NULL DEFAULT '',
                        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('buyer', 'seller', 'admin')),
                        phone TEXT NOT NULL DEFAULT '',
                        business_type TEXT NOT NULL DEFAULT '',
                        whatsapp_number TEXT NOT NULL DEFAULT '',
                        google_subject TEXT UNIQUE,
                        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    )
                    """
                )
                connection.execute(
                    f"""
                    INSERT INTO users_new (
                        id, full_name, email, password_hash, role, phone,
                        business_type, whatsapp_number, google_subject, created_at
                    )
                    SELECT id, {full_name}, email, password_hash, role, {phone},
                           {business_type}, {whatsapp_number}, {google_subject}, created_at
                    FROM users
                    """
                )
                connection.execute("DROP TABLE users")
                connection.execute("ALTER TABLE users_new RENAME TO users")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.execute("PRAGMA legacy_alter_table = OFF")
                connection.execute("PRAGMA foreign_keys = ON")
        product_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(products)")
        }
        migrations = {
            "brand": "TEXT NOT NULL DEFAULT 'Maison Muse'",
            "sku": "TEXT",
            "old_price": "REAL",
            "discount": "TEXT NOT NULL DEFAULT ''",
            "reviews_count": "INTEGER NOT NULL DEFAULT 0",
            "tag_color": "TEXT NOT NULL DEFAULT ''",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
            "low_stock_threshold": "INTEGER NOT NULL DEFAULT 5",
            "active": "INTEGER NOT NULL DEFAULT 1",
            "unit_cost": "REAL NOT NULL DEFAULT 0 CHECK (unit_cost >= 0)",
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "variants_json": "TEXT NOT NULL DEFAULT '[]'",
            "product_status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
            "title": "TEXT NOT NULL DEFAULT ''",
            "slug": "TEXT NOT NULL DEFAULT ''",
            "category_slug": "TEXT NOT NULL DEFAULT ''",
            "sub_category": "TEXT NOT NULL DEFAULT ''",
            "features_json": "TEXT NOT NULL DEFAULT '[]'",
            "image_url": "TEXT NOT NULL DEFAULT ''",
            "seller_name": "TEXT NOT NULL DEFAULT ''",
            "seller_slug": "TEXT NOT NULL DEFAULT ''",
            "seller_phone": "TEXT NOT NULL DEFAULT ''",
            "is_agri_product": "INTEGER NOT NULL DEFAULT 0 CHECK (is_agri_product IN (0, 1))",
            "farmer_name": "TEXT NOT NULL DEFAULT ''",
            "farmer_whatsapp": "TEXT NOT NULL DEFAULT ''",
            "seller_whatsapp_phone": "TEXT NOT NULL DEFAULT ''",
            "seller_verified": "INTEGER NOT NULL DEFAULT 0 CHECK (seller_verified IN (0, 1))",
            "boosted_until": "TEXT NOT NULL DEFAULT ''",
            "fulfillment_mode": "TEXT NOT NULL DEFAULT 'SELF_FULFILLMENT'",
            "qc_status": "TEXT NOT NULL DEFAULT 'APPROVED_LIVE'",
        }
        for column, definition in migrations.items():
            if column not in product_columns:
                connection.execute(f"ALTER TABLE products ADD COLUMN {column} {definition}")
        connection.execute(
            "UPDATE products SET is_agri_product = 1 WHERE category IN "
            "('Veterinary Medicines', 'Dairy Cattle', 'Goats & Sheep', 'Poultry & Fowl')"
        )
        connection.execute("UPDATE products SET title = name WHERE title = ''")
        connection.execute("UPDATE products SET image_url = image WHERE image_url = ''")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_slug ON products(slug) WHERE slug != ''"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_category_slug ON products(category_slug, active, product_status)"
        )
        order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(orders)")
        }
        for column, definition in {
            "tracking_id": "TEXT NOT NULL DEFAULT ''",
            "buyer_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in order_columns:
                connection.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")
        connection.execute(
            "UPDATE orders SET updated_at = created_at WHERE updated_at = ''"
        )
        connection.execute(
            "UPDATE orders SET tracking_id = order_number WHERE tracking_id = ''"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_tracking_id
            ON orders(tracking_id) WHERE tracking_id != ''
            """
        )
        if "mpesa_phone" not in order_columns:
            connection.execute(
                "ALTER TABLE orders ADD COLUMN mpesa_phone TEXT NOT NULL DEFAULT ''"
            )
        if "seller_id" not in product_columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN seller_id INTEGER REFERENCES sellers(id) ON DELETE SET NULL"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id, active, name)"
        )
        seller_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sellers)")
        }
        seller_migrations = {
            "store_bio": "TEXT NOT NULL DEFAULT ''",
            "business_category": "TEXT NOT NULL DEFAULT ''",
            "business_type": "TEXT NOT NULL DEFAULT ''",
            "whatsapp_phone": "TEXT NOT NULL DEFAULT ''",
            "whatsapp_number": "TEXT NOT NULL DEFAULT ''",
            "instagram_url": "TEXT NOT NULL DEFAULT ''",
            "tiktok_url": "TEXT NOT NULL DEFAULT ''",
            "operating_hours": "TEXT NOT NULL DEFAULT ''",
            "holiday_mode": "INTEGER NOT NULL DEFAULT 0 CHECK (holiday_mode IN (0, 1))",
            "city": "TEXT NOT NULL DEFAULT ''",
            "business_registration_number": "TEXT NOT NULL DEFAULT ''",
            "owner_name": "TEXT NOT NULL DEFAULT ''",
            "submitted_documents_json": "TEXT NOT NULL DEFAULT '[]'",
            "review_note": "TEXT NOT NULL DEFAULT ''",
            "review_state": "TEXT NOT NULL DEFAULT 'CLEAR' CHECK (review_state IN ('CLEAR', 'UNDER_AUDIT'))",
            "commission_is_custom": "INTEGER NOT NULL DEFAULT 0 CHECK (commission_is_custom IN (0, 1))",
            "accepted_terms": "INTEGER NOT NULL DEFAULT 0 CHECK (accepted_terms IN (0, 1))",
            "selected_plan": "TEXT CHECK (selected_plan IS NULL OR selected_plan IN ('boutique', 'pro', 'enterprise'))",
            "commission_rate": "REAL NOT NULL DEFAULT 10 CHECK (commission_rate BETWEEN 0 AND 100)",
        }
        for column, definition in seller_migrations.items():
            if column not in seller_columns:
                connection.execute(f"ALTER TABLE sellers ADD COLUMN {column} {definition}")
        sub_order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sub_orders)")
        }
        for column, definition in {
            "courier_name": "TEXT NOT NULL DEFAULT ''",
            "tracking_number": "TEXT NOT NULL DEFAULT ''",
            "admin_override_status": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in sub_order_columns:
                connection.execute(f"ALTER TABLE sub_orders ADD COLUMN {column} {definition}")
        connection.execute(
            "UPDATE sub_orders SET updated_at = created_at WHERE updated_at = ''"
        )
        seller_profile_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(seller_profiles)")
        }
        seller_profile_migrations = {
            "business_category": "TEXT NOT NULL DEFAULT ''",
            "business_registration_number": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in seller_profile_migrations.items():
            if column not in seller_profile_columns:
                connection.execute(
                    f"ALTER TABLE seller_profiles ADD COLUMN {column} {definition}"
                )
        sub_order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sub_orders)")
        }
        for column, definition in {
            "dispatched_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if column not in sub_order_columns:
                connection.execute(f"ALTER TABLE sub_orders ADD COLUMN {column} {definition}")
        promotion_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(seller_promotions)")
        }
        if "product_ids_json" not in promotion_columns:
            connection.execute(
                "ALTER TABLE seller_promotions ADD COLUMN product_ids_json TEXT NOT NULL DEFAULT '[]'"
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO seller_profiles (
                user_id, seller_id, store_name, store_slug, business_phone,
                payout_number, business_category, business_registration_number, status
            )
            SELECT s.user_id, s.id, s.store_name, s.store_slug, s.business_phone,
                   s.payout_account, s.business_category,
                   s.business_registration_number,
                   CASE WHEN s.status = 'APPROVED' THEN 'approved' ELSE 'pending' END
            FROM sellers s
            """
        )
        payout_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(payout_transactions)")
        }
        payout_migrations = {
            "commission_retained": "REAL NOT NULL DEFAULT 0 CHECK (commission_retained >= 0)",
            "status": "TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED', 'FAILED', 'PROCESSING'))",
            "transaction_id": "TEXT NOT NULL DEFAULT ''",
            "failure_reason": "TEXT NOT NULL DEFAULT ''",
            "destination_type": "TEXT NOT NULL DEFAULT 'registered_phone'",
            "destination_hint": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in payout_migrations.items():
            if column not in payout_columns:
                connection.execute(
                    f"ALTER TABLE payout_transactions ADD COLUMN {column} {definition}"
                )
        ledger_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(seller_payout_ledger)")
        }
        if "paid_amount" not in ledger_columns:
            connection.execute(
                "ALTER TABLE seller_payout_ledger ADD COLUMN paid_amount REAL NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            UPDATE seller_payout_ledger
            SET paid_amount = net_amount
            WHERE status = 'PAID (DEMO)' AND paid_amount = 0
            """
        )
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        connection.execute(
            "UPDATE orders SET status = 'pending' WHERE status = 'demo_received'"
        )
        order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(orders)")
        }
        if "payment_attempts" not in order_columns:
            connection.execute(
                "ALTER TABLE orders ADD COLUMN payment_attempts INTEGER NOT NULL DEFAULT 0"
            )
        order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(orders)")
        }
        order_payment_migrations = {
            "payment_gateway": "TEXT NOT NULL DEFAULT ''",
            "gateway_reference": "TEXT NOT NULL DEFAULT ''",
            "gateway_tracking_id": "TEXT NOT NULL DEFAULT ''",
            "gateway_status": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in order_payment_migrations.items():
            if column not in order_columns:
                connection.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")

        order_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'orders'"
        ).fetchone()["sql"]
        if "pesapal" not in order_table_sql.casefold():
            connection.commit()
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA legacy_alter_table = ON")
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ALTER TABLE orders RENAME TO orders_legacy")
                connection.execute(
                    """
                    CREATE TABLE orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_number TEXT NOT NULL UNIQUE,
                        tracking_id TEXT NOT NULL DEFAULT '',
                        buyer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        customer_name TEXT NOT NULL,
                        customer_phone TEXT NOT NULL,
                        delivery_address TEXT NOT NULL,
                        payment_method TEXT NOT NULL
                            CHECK (payment_method IN ('mobile-money', 'card', 'pesapal')),
                        payment_gateway TEXT NOT NULL DEFAULT '',
                        gateway_reference TEXT NOT NULL DEFAULT '',
                        gateway_tracking_id TEXT NOT NULL DEFAULT '',
                        gateway_status TEXT NOT NULL DEFAULT '',
                        mpesa_phone TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL,
                        payment_status TEXT NOT NULL,
                        subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
                        shipping_cents INTEGER NOT NULL CHECK (shipping_cents >= 0),
                        tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
                        total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
                        payment_attempts INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO orders (
                        id, order_number, tracking_id, buyer_id, customer_name, customer_phone,
                        delivery_address, payment_method, payment_gateway,
                        gateway_reference, gateway_tracking_id, gateway_status,
                        mpesa_phone,
                        status, payment_status, subtotal_cents, shipping_cents,
                        tax_cents, total_cents, payment_attempts, created_at,
                        updated_at
                    )
                    SELECT
                        id, order_number, tracking_id, buyer_id, customer_name, customer_phone,
                        delivery_address, payment_method, payment_gateway,
                        gateway_reference, gateway_tracking_id, gateway_status,
                        mpesa_phone,
                        status, payment_status, subtotal_cents, shipping_cents,
                        tax_cents, total_cents, payment_attempts, created_at,
                        updated_at
                    FROM orders_legacy
                    """
                )
                connection.execute("DROP TABLE orders_legacy")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.execute("PRAGMA legacy_alter_table = OFF")
                connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_tracking_id
            ON orders(tracking_id) WHERE tracking_id != ''
            """
        )
        all_access = {
            "products": {"read": True, "write": True, "delete": True},
            "orders": {"read": True, "write": True, "delete": True},
            "analytics": {"read": True, "write": True, "delete": True},
            "settings": {"read": True, "write": True, "delete": True},
        }
        default_roles = {
            "Super Admin": all_access,
            "Store Manager": {
                "products": {"read": True, "write": True, "delete": True},
                "orders": {"read": True, "write": True, "delete": False},
                "analytics": {"read": True, "write": False, "delete": False},
                "settings": {"read": True, "write": False, "delete": False},
                "support": {"read": True, "write": False},
            },
            "Support Agent": {
                "products": {"read": True, "write": False, "delete": False},
                "orders": {"read": True, "write": True, "delete": False},
                "analytics": {"read": False, "write": False, "delete": False},
                "settings": {"read": False, "write": False, "delete": False},
                "support": {"read": True, "write": True},
            },
            "Inventory Clerk": {
                "products": {"read": True, "write": True, "delete": False},
                "orders": {"read": False, "write": False, "delete": False},
                "analytics": {"read": False, "write": False, "delete": False},
                "settings": {"read": False, "write": False, "delete": False},
                "support": {"read": False, "write": False},
            },
        }
        all_access["support"] = {"read": True, "write": True}
        connection.executemany(
            """
            INSERT OR IGNORE INTO admin_role_permissions (role, permissions_json)
            VALUES (?, ?)
            """,
            [
                (role, json.dumps(permissions))
                for role, permissions in default_roles.items()
            ],
        )
        for role, permissions_json in connection.execute(
            "SELECT role, permissions_json FROM admin_role_permissions"
        ).fetchall():
            permissions = json.loads(permissions_json)
            if "support" not in permissions:
                permissions["support"] = default_roles.get(role, {}).get(
                    "support", {"read": False, "write": False}
                )
                connection.execute(
                    "UPDATE admin_role_permissions SET permissions_json = ? WHERE role = ?",
                    (json.dumps(permissions), role),
                )
        connection.execute(
            """
            INSERT OR IGNORE INTO store_settings (key, value)
            VALUES ('marketplace_default_commission', '10')
            """
        )

        from app.catalog_seed import seed_products

        seed_products(connection)
        connection.commit()


def decode_json_array(value: str) -> list:
    decoded = json.loads(value)
    return decoded if isinstance(decoded, list) else []
