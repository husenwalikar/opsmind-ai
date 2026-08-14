"""
ShopFlow E-Commerce Microservice — Core API Server
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from test_bed.app.database import init_db, list_products
from test_bed.app.logger import get_structured_logger
from test_bed.app.services.auth import verify_user_permissions
from test_bed.app.services.billing import calculate_order_summary
from test_bed.app.services.checkout import process_order_checkout
from test_bed.app.services.gateway import dispatch_card_charge
from test_bed.app.services.inventory import allocate_warehouse_facility
from test_bed.app.services.promotions import evaluate_coupon_discount

load_dotenv("test_bed/.env")

log = get_structured_logger("shopflow.api")


# ── Request / Response Schemas ────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    coupon_code: Optional[str] = None
    customer_payload: Dict[str, Any] = {}
    warehouse_tier: int = 0

class AuthRequest(BaseModel):
    session_token: Optional[str] = None

class PromotionRequest(BaseModel):
    coupon_code: str
    base_amount: float

class PaymentRequest(BaseModel):
    order_id: str
    amount: float
    simulate_network_hang: bool = False


# ── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("ShopFlow application initialized successfully")
    yield

app = FastAPI(title="ShopFlow API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="test_bed/app/static"), name="static")


# ── Standard Request & Error Logging Middleware ───────────────────────────────

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        log.error(
            f"Unhandled exception during {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )


# ── Storefront & Business Endpoints ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def storefront():
    with open("test_bed/app/static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "shopflow-api"}

@app.get("/api/products")
async def get_products():
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "price": p.price,
                "category": p.category,
                "stock": p.stock,
                "emoji": p.emoji,
            }
            for p in list_products()
        ]
    }

@app.post("/api/checkout")
async def checkout(req: CheckoutRequest):
    discount = evaluate_coupon_discount(req.coupon_code, 500.0) if req.coupon_code else 0.0
    summary = calculate_order_summary(subtotal=500.0, discount_amount=discount)
    facility = allocate_warehouse_facility(req.warehouse_tier)
    order = process_order_checkout(summary.total_payable, req.customer_payload)
    return {
        "order": order.model_dump(),
        "billing": summary.model_dump(),
        "facility": facility,
    }

@app.post("/api/auth/verify")
async def verify_session(req: AuthRequest):
    return {"role": verify_user_permissions(req.session_token)}

@app.post("/api/promotions/apply")
async def apply_promotion(req: PromotionRequest):
    return {"discount": evaluate_coupon_discount(req.coupon_code, req.base_amount)}

@app.post("/api/payment/charge")
async def charge(req: PaymentRequest):
    return dispatch_card_charge(req.order_id, req.amount, req.simulate_network_hang)
