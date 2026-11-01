import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_ROOT, get_cors_origins
from app.database import get_connection, initialize_database
from app.routers import (
    admin,
    auth,
    newsletter,
    orders,
    payments,
    products,
    seller_features,
    sellers,
    support,
    verified_sellers,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class SupportConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = {}
        self.admin_connections: dict[str, set[WebSocket]] = {}

    async def connect(
        self, ticket_id: str, websocket: WebSocket, is_admin: bool = False
    ) -> None:
        await websocket.accept()
        self.connections.setdefault(ticket_id, set()).add(websocket)
        if is_admin:
            self.admin_connections.setdefault(ticket_id, set()).add(websocket)
            await self.broadcast(
                ticket_id,
                {
                    "type": "presence",
                    "agents_online": len(self.admin_connections[ticket_id]),
                },
            )

    def disconnect(self, ticket_id: str, websocket: WebSocket) -> bool:
        active = self.connections.get(ticket_id)
        if active is not None:
            active.discard(websocket)
            if not active:
                self.connections.pop(ticket_id, None)
        admins = self.admin_connections.get(ticket_id)
        was_admin = admins is not None and websocket in admins
        if admins is not None:
            admins.discard(websocket)
            if not admins:
                self.admin_connections.pop(ticket_id, None)
        return was_admin

    async def broadcast(self, ticket_id: str, event: dict) -> None:
        for websocket in tuple(self.connections.get(ticket_id, set())):
            try:
                await websocket.send_json(event)
            except (RuntimeError, OSError):
                self.disconnect(ticket_id, websocket)


class OrderConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, tracking_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(tracking_id, set()).add(websocket)

    def disconnect(self, tracking_id: str, websocket: WebSocket) -> None:
        connections = self.connections.get(tracking_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self.connections.pop(tracking_id, None)

    def publish(self, tracking_id: str, event: dict) -> None:
        if self.loop is None or self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.broadcast(tracking_id, event))
        )

    async def broadcast(self, tracking_id: str, event: dict) -> None:
        for websocket in tuple(self.connections.get(tracking_id, set())):
            try:
                await websocket.send_json(event)
            except (RuntimeError, OSError):
                self.disconnect(tracking_id, websocket)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    application.state.order_connections.loop = asyncio.get_running_loop()
    yield


def create_app() -> FastAPI:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    application = FastAPI(
        title="Maison Muse API",
        description="Python REST API for the Maison Muse storefront.",
        version="1.0.0",
        lifespan=lifespan,
    )
    origins = get_cors_origins()
    application.state.cors_origins = origins
    application.state.support_connections = SupportConnectionManager()
    application.state.order_connections = OrderConnectionManager()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "X-Admin-Request",
            "X-Seller-Request",
            "X-Support-Token",
            "Authorization",
        ],
    )
    application.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    application.include_router(products.router, prefix="/api", tags=["products"])
    application.include_router(orders.router, prefix="/api", tags=["orders"])
    application.include_router(sellers.router, prefix="/api/seller", tags=["sellers"])
    application.include_router(
        seller_features.router, prefix="/api", tags=["seller-tools"]
    )
    application.include_router(
        verified_sellers.router, prefix="/api/sellers", tags=["sellers"]
    )
    application.include_router(payments.router, prefix="/api", tags=["payments"])
    application.include_router(newsletter.router, prefix="/api", tags=["newsletter"])
    application.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    application.include_router(support.router, prefix="/api", tags=["support"])
    application.include_router(
        support.websocket_router, tags=["support-websocket"]
    )
    application.mount(
        "/uploads",
        StaticFiles(directory=str(UPLOAD_ROOT)),
        name="seller-uploads",
    )

    @application.websocket("/ws/orders/{order_id}")
    async def order_updates(websocket: WebSocket, order_id: str) -> None:
        with get_connection() as connection:
            order = connection.execute(
                """
                SELECT id, tracking_id, status FROM orders
                WHERE tracking_id = ? OR order_number = ?
                """,
                (order_id, order_id),
            ).fetchone()
            if order is None:
                await websocket.close(code=4404)
                return
            latest = connection.execute(
                """
                SELECT COALESCE(
                    NULLIF(admin_override_status, ''),
                    CASE fulfillment_status
                        WHEN 'PENDING' THEN 'PENDING_PACKING'
                        WHEN 'PROCESSING' THEN 'PACKED'
                        WHEN 'SHIPPED' THEN 'DISPATCHED_TO_COURIER'
                        ELSE fulfillment_status
                    END
                ) AS status
                FROM sub_orders
                WHERE parent_order_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (order["id"],),
            ).fetchone()

        tracking_id = order["tracking_id"]
        manager: OrderConnectionManager = websocket.app.state.order_connections
        await manager.connect(tracking_id, websocket)
        await websocket.send_json(
            {
                "type": "connected",
                "tracking_id": tracking_id,
                "status": latest["status"] if latest else order["status"],
            }
        )
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(tracking_id, websocket)

    @application.get("/api/health", tags=["health"])
    def health_check() -> dict[str, str]:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "database": "connected"}

    return application


app = create_app()
