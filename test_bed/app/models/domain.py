"""
Domain Data Contracts & Pydantic Schemas for ShopFlow Microservice
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    category: str
    stock: int


class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class OrderSummary(BaseModel):
    subtotal: float
    tax: float
    discount_amount: float
    total_payable: float
    effective_discount_ratio: float


class CheckoutRequest(BaseModel):
    customer_id: Optional[str] = None
    items: List[CartItem]
    coupon_code: Optional[str] = None
    customer_payload: Dict[str, Any] = Field(default_factory=dict)


class OrderConfirmation(BaseModel):
    order_id: str
    total_amount: float
    status: str
    fulfillment_tier: str
    shipping_destination: str