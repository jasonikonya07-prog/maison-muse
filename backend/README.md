# Maison Muse Python API

This FastAPI service powers the storefront catalog and processes orders through
Pesapal API 3.0. It
uses SQLite for local development by default, or PostgreSQL when `DATABASE_URL`
is configured. Its catalog synchronizes from
`frontend/src/data/products.json` at startup. The shared catalog contains 25
products across perfumes and fragrances, press-on nails, skincare and glow,
lip and makeup essentials, and hair and accessories.

## Requirements

- Python 3.10 or newer
- pip

## Run on Windows

From the repository root in PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set AUTH_JWT_SECRET in .env to a unique random value of at least 32 characters.
# Generate a Fernet key with this virtual environment's Python, then set DATA_ENCRYPTION_KEY in .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep `DATA_ENCRYPTION_KEY` private and backed up. If this API connects to the
same encrypted database in multiple environments, configure the same key in
each environment; losing or changing it makes encrypted values unreadable.

The API is available at `http://127.0.0.1:8000`. Interactive API
documentation is at `http://127.0.0.1:8000/docs`.

The frontend's Vite development proxy already forwards `/api` requests to this
address. To use a different backend host, set `VITE_API_PROXY_TARGET` in
`frontend/.env.local`.

## Deploy frontend to Vercel and API to Render

The deployment configuration is in `frontend/vercel.json` and the repository
root `render.yaml`.

### Render API

1. Rotate any database password shared in chat, then create the new Supabase
   transaction-pooler URL. Do not put database credentials in source files or
   share them in chat.
2. Before deploying the API, import the existing local database into the
   empty Supabase database using the steps in **Migrate SQLite data to
   Supabase** below. Use the rotated `DATABASE_URL` privately for the one-time
   import. Do not import into a database already containing live marketplace
   records.
3. In Render, create a Blueprint from this repository and review the service
   settings before applying. It deploys `maison-muse-api` from `backend/`,
   installs `backend/requirements.txt`, runs Uvicorn on Render's assigned port,
   and checks `/api/health`.
   If an existing service reports that `requirements.txt` is missing, set its
   **Root Directory** to `backend` (or recreate it from the repository
   Blueprint); the build command `pip install -r requirements.txt` is relative
   to that directory.
4. Add the prompted secret values in Render. Set `DATABASE_URL` to the URL with
   the rotated password and `CORS_ORIGINS` to the exact Vercel production
   origin(s), comma-separated and without trailing slashes. Add a strong unique
   `ADMIN_USERNAME`/`ADMIN_PASSWORD`, a matching Google OAuth client ID, and
   payment credentials/URLs if enabling Pesapal. Keep Pesapal in sandbox until
   merchant onboarding is complete.
5. The blueprint provisions a 1 GB persistent disk for seller image uploads.
   Render persistent disks require a paid web-service instance and keep the API
   to one instance; the support/order WebSockets also use in-process state, so
   do not scale this service horizontally without adding shared storage and
   pub/sub.

### Vercel storefront

1. Import the repository in Vercel and set the project **Root Directory** to
   `frontend`. Vercel uses `frontend/vercel.json` for client-side route
   fallback and proxies `/api/admin/*` through the Vercel origin so the
   administrator's HTTP-only session cookie works with the API hosted on
   Render; the Vite build outputs to `dist`.
2. Set `VITE_API_BASE_URL` to the Render API origin, e.g.
   `https://maison-muse-api.onrender.com` (no trailing slash). Set
   `VITE_GOOGLE_CLIENT_ID` to the same web client ID used by the backend.
   These are frontend build variables, not backend secrets.
3. Deploy the site, copy its exact production domain (and any `www` domain),
   then set those origins in Render's `CORS_ORIGINS` and redeploy the API.
4. In Google Cloud Console, add the Vercel domain to the OAuth web client's
   authorized JavaScript origins. For Pesapal, use the public Vercel return
   URL and Render IPN URL, register the IPN URL with Pesapal, and configure
   the resulting IPN ID in Render.

Do not set `VITE_API_BASE_URL` to a Supabase URL: the browser must call the
FastAPI service, which connects to Supabase privately. Supabase credentials
belong only in Render's `DATABASE_URL` secret.

## Endpoints

- `GET /api/health` — verifies the API and database are available.
- `GET /api/products` — lists products; supports `search`, `category`, `limit`,
  and `offset` query parameters.
- `GET /api/products/categories` — lists catalog categories.
- `GET /api/products/{product_id}` — returns one product.
- `POST /api/auth/register` and `POST /api/auth/login` — create buyer/seller
  accounts or return a signed JWT and sanitized profile. Public registration
  only accepts buyer or seller roles; seller registrations create a pending
  marketplace application.
- `POST /api/auth/google` — verifies a Google Identity Services ID token and
  signs in verified buyer accounts only. Existing password accounts are not
  silently linked to Google identities.
- `GET /api/auth/me` — returns the profile for a valid bearer token.
- `POST /api/seller/register` and `POST /api/seller/login` — create a seller
  application or start an HttpOnly seller session. Registration accepts HTTPS
  logo/banner image URLs and M-Pesa or bank payout details. Both, as well as
  seller-authenticated APIs, are blocked while global Seller Portal maintenance
  is enabled.
- `GET /api/seller/portal-status` — public Seller Portal maintenance notice.
- `GET /api/seller/me` and `GET /api/seller/dashboard` — return the signed-in
  seller profile and analytics. Seller product and order operations are scoped
  to the signed-in seller; inventory and fulfillment writes require an approved
  seller account.
- `GET /api/seller/stores/{store_slug}` — public approved-vendor profile and
  catalog for the `/store/{store_slug}` storefront page.
- `POST /api/support/message` — knowledge-guided support automation for
  storefront, seller, payment, delivery, and order questions. It does not send
  conversations to a third-party AI provider or use customer chats for model
  training. Credential-like content is not saved as chat text, and contact
  details in message text are redacted; cancellation/refund decisions are
  handed to support agents.
- `GET /api/admin/marketplace` — administrator marketplace verification queue,
  earned commissions, pending eligible payouts, and payout ledger.
- `PATCH /api/admin/marketplace/seller-portal-maintenance` — globally block or
  restore seller access to Seller Studio; admin access remains available.
- `PATCH /api/admin/marketplace/vendors/{seller_id}` — approve, reject
  (suspend), or suspend a seller application.
- `POST /api/admin/marketplace/vendors/{seller_id}/review` — approve, reject
  with a reason, request additional information, suspend, restore, or place a
  seller under audit. Review decisions are written to the immutable audit log.
- `GET/PUT /api/admin/marketplace/commissions` — read and update the global,
  category-specific, seller-specific, and seller/category commission policy.
  Commission updates apply to new orders and are audited.
- `GET /api/admin/marketplace/orders` and
  `GET /api/admin/marketplace/orders/sellers` — inspect seller sub-orders
  alongside their parent customer order.
- `POST /api/admin/marketplace/orders/{sub_order_id}/disputes` — record refund,
  return, and vendor-penalty resolution actions with an audit record.
- `GET /api/admin/marketplace/analytics` — marketplace GMV, commissions,
  recorded completed payouts, active sellers, and vendor rankings.
- `POST /api/admin/marketplace/payouts` — record a completed payout for
  selected paid and delivered seller sub-orders. The server calculates the
  payable amount, queues a `PROCESSING` dispatch, and prevents an order from
  being paid twice.
- `PATCH /api/admin/marketplace/payouts/{payout_id}` — record a completed or
  failed external dispatch. A transaction ID is required to mark it completed;
  failed dispatches release their sub-orders so they can be retried.
- `POST /api/orders` — validates current catalog prices and stock, creates a
  pending order, groups vendor line items into seller sub-orders, and returns a
  Pesapal hosted-checkout URL.
- `GET /api/payments/pesapal/status` — verifies the returned transaction
  directly with Pesapal.
- `GET /api/payments/pesapal/ipn` — receives Pesapal IPN notifications and
  verifies status server-to-server before changing payment state.
- `POST /api/newsletter` — validates an email address and saves the signup to
  the configured database. Email campaign delivery is not configured.

An order request has this shape:

```json
{
  "customer": {
    "name": "Jamie Rivers",
    "phone": "+1 555 123 4567",
    "address": "18 Garden Lane, Portland"
  },
  "items": [
    {
      "product_id": "perf-03",
      "quantity": 1,
      "variant": ""
    }
  ]
}
```

Seller writes use either a signed seller bearer token or the legacy
`maison_muse_seller` HttpOnly cookie, an approved storefront `Origin`, and the
`X-Seller-Request: 1` header. Admin marketplace
management uses the existing administrator session, origin validation, and
`X-Admin-Request: 1`; the payout account is only returned to administrators
with marketplace write permission. Set `ADMIN_COOKIE_SECURE=true` when serving
the application over HTTPS.

Order totals are calculated by the API, not trusted from the browser. Card and
mobile-wallet credentials are entered only on Pesapal's hosted checkout and
must never be sent to this API. An order remains unpaid until the API verifies
the provider's transaction status, amount, and currency. Configure Pesapal below
before enabling checkout in production.
Catalog and order prices are denominated in Kenyan shillings (KES). Shipping
is KSh 250 below KSh 5,000 and complimentary at or above that
threshold; the estimate includes 8% tax.

## Configuration

Copy `.env.example` to `.env`, set the Pesapal and other required values, and
configure `DATABASE_PATH`, `DATABASE_URL`, or `CORS_ORIGINS` as needed. The application reads
environment variables directly; for convenience, the example values can also
be exported in the shell before starting Uvicorn.
Without `DATABASE_URL`, SQLite is created at
`backend/data/maison_muse.sqlite3`. In production, set `DATABASE_URL` to the
Supabase PostgreSQL transaction-pooler connection string. Keep it private and
store it as a Render environment secret; do not commit it or put it in the
frontend.

For PostgreSQL, also set `DATA_ENCRYPTION_KEY` to a private Fernet key. Generate
one once from the `backend` directory:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put that key in `backend/.env` for local work and in Render's
`DATA_ENCRYPTION_KEY` secret. Use the **same key** anywhere that connects to this
database, keep a secure backup, and never commit or share it. The API encrypts
phone numbers, delivery and branch addresses, and seller payout/contact fields
before PostgreSQL stores them; it decrypts them for existing application
workflows. On startup it also encrypts existing plaintext values. PostgreSQL
startup fails if the key is missing or cannot decrypt stored data. Key loss
means the encrypted values cannot be recovered.
Order phone matching uses a keyed one-way lookup hash, not plaintext. Do not
change the key without a planned data re-encryption and lookup-index migration.
This field encryption applies to PostgreSQL; local SQLite development databases
remain plaintext and should be kept private.

### Migrate SQLite data to Supabase

1. In Supabase, open **Connect** and copy the PostgreSQL transaction-pooler
   connection string. Use the pooler URL for a Render deployment and keep the
   database password private.
2. Before deploying or migrating, configure both `DATABASE_URL` and the
   generated `DATA_ENCRYPTION_KEY` in `backend/.env` (or in the PowerShell
   session that runs the migration). Never share either secret or commit them.
3. From the `backend` directory, preview the local source database:

   ```powershell
   python -m app.migrate_sqlite_to_postgres
   ```

4. Confirm the new Supabase app schema is empty, then import the local database:

   ```powershell
   python -m app.migrate_sqlite_to_postgres --apply
   ```

   The importer refuses to overwrite data in the destination. It copies
   application tables in foreign-key order, preserves category hierarchies,
   resets generated ID sequences, and does not migrate active admin or seller
   sessions. Users will need to sign in again.
5. In Render, set the same `DATABASE_URL` and `DATA_ENCRYPTION_KEY` under the
   FastAPI service's environment variables and redeploy. The API creates/updates
   its schema and encrypts any existing plaintext sensitive fields on startup.
   Leave `DATABASE_PATH` unset in production.

Keep the local SQLite file as a backup until you verify sign-in, products,
orders, seller tools, support, and admin pages against the hosted API. Do not
run the import again after live data has been written to Supabase.

### Buyer and seller authentication

Set `AUTH_JWT_SECRET` to a unique random value of at least 32 characters before
enabling `/api/auth/register` or `/api/auth/login`. For example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The storefront saves the returned JWT and sanitized profile in browser
`localStorage`, and seller API requests send the JWT as a bearer token. Serve
the site over HTTPS and protect it against cross-site scripting. Admin console
access remains on its separate server-managed admin session.

To enable buyer-only Google sign-in, create a Google Identity Services web
client, set its client ID in both `backend/.env` as `GOOGLE_CLIENT_ID` and
`frontend/.env.local` as `VITE_GOOGLE_CLIENT_ID`, then restart the API and
frontend. The backend verifies each Google ID token with Google's token
verification endpoint; browser-supplied profile fields are not trusted.

### Pesapal setup

1. Create a Pesapal merchant account and obtain API 3.0 consumer credentials.
   Start with `PESAPAL_ENVIRONMENT=sandbox`; use `live` only with live
   credentials and after completing merchant onboarding.
2. Set `PESAPAL_CALLBACK_URL` to the public storefront URL ending in
   `/checkout/pesapal-return`. Set `PESAPAL_IPN_URL` to the public API URL
   ending in `/api/payments/pesapal/ipn`. The live URLs must use HTTPS.
3. Register the IPN URL once from the backend directory:

   ```powershell
   python -m app.pesapal_setup
   ```

   Copy the returned ID into `PESAPAL_IPN_ID` in `backend/.env`, then restart
   the API.
4. Configure the production storefront and API origins, restart both services,
   and complete a sandbox transaction before switching credentials and
   environment to live.

The backend sends order submissions and status requests to Pesapal; secrets
remain in the backend environment. The browser only receives the hosted
checkout URL. Payment-return query parameters are treated as untrusted: the
backend fetches the transaction from Pesapal and checks its amount/currency
before marking the order paid. Admin reconciliation performs the same provider
status verification.

### Admin dashboard

The dashboard is available at `/admin`. Configure all of the following in
`backend/.env` before signing in:

- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: unique administrator credentials.
- `ADMIN_SESSION_SECRET`: a private random value of at least 32 characters.
- `ADMIN_ROLE`: `Super Admin`, `Store Manager`, `Support Agent`, or
  `Inventory Clerk`; defaults to `Super Admin`.
- `ADMIN_COOKIE_SECURE`: set to `true` when the site is served over HTTPS;
  leave it `false` only for local HTTP development.
- `CORS_ORIGINS`: include the exact origin serving the frontend.

Generate a session secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Use a long, unique password and rotate any credential disclosed in chat before
deployment. Do not commit `.env` or expose these values to the frontend. Admin
writes require an authenticated session cookie, an approved `Origin`, and the
`X-Admin-Request` header. Product changes, inventory, order statuses, campaigns, and store availability
are persisted in the configured database.

Administrator sessions are server-tracked and revocable. Failed logins are
rate-limited by source IP. Role permissions are enforced by the API, and audit
events are stored in an append-only database table. `ADMIN_ROLE` assigns the
configured environment account; creating and managing separate staff identities
requires an identity-provider or account-provisioning integration.

The security center can revoke sessions and adjust permissions. Payment
reconciliation queries Pesapal directly. Abandoned-cart
recovery actions remain disabled because the storefront does not collect
pre-purchase contact data or integrate email/WhatsApp delivery. Risk scores are
review signals only. Supplier COGS and purchase-order drafts are available, but
drafts are not sent to suppliers.

Maintenance mode is reflected by the public storefront status endpoint and
displays a temporary maintenance page to shoppers. Campaigns expire in the
database after their configured duration. Campaign discounts are currently
administrative metadata only and are not applied to storefront prices or
checkout.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```
