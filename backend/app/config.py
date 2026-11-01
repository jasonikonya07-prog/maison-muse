import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_ROOT = BACKEND_ROOT / "uploads"


def get_database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH", "data/maison_muse.sqlite3")
    path = Path(configured_path)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


def demo_seller_approval_enabled() -> bool:
    environment = os.getenv("APP_ENV", "production").strip().casefold()
    enabled = os.getenv("SELLER_DEMO_APPROVAL_ENABLED", "false").strip().casefold()
    return environment in {"development", "dev", "local"} and enabled == "true"


def auto_approve_seller_registrations_enabled() -> bool:
    enabled = os.getenv("SELLER_AUTO_APPROVE_REGISTRATIONS", "false").strip().casefold()
    return demo_seller_approval_enabled() and enabled == "true"
