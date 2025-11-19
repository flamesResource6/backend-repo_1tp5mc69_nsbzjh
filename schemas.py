"""
Database Schemas

FoodKasir collections using Pydantic models.
Each model name (lowercased) is used as the MongoDB collection name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class Menuitem(BaseModel):
    """
    Menu items available for ordering
    Collection: "menuitem"
    """
    name: str = Field(..., description="Menu item name")
    category: Optional[str] = Field(None, description="Category e.g., Drinks, Food")
    price: float = Field(..., ge=0, description="Price per unit")
    image_url: Optional[str] = Field(None, description="Optional image URL")
    is_active: bool = Field(True, description="Whether item is available")

class OrderItem(BaseModel):
    item_id: str = Field(..., description="Referenced menu item _id as string")
    name: str = Field(..., description="Snapshot of item name at order time")
    price: float = Field(..., ge=0, description="Snapshot of unit price at order time")
    quantity: int = Field(..., ge=1, description="Quantity ordered")
    subtotal: float = Field(..., ge=0, description="price * quantity")

class Order(BaseModel):
    """
    Orders placed by cashier
    Collection: "order"
    """
    items: List[OrderItem] = Field(..., description="List of items in the order")
    total: float = Field(..., ge=0, description="Total amount for the order")
    note: Optional[str] = Field(None, description="Optional note")
    payment_method: Optional[str] = Field(None, description="Cash, QRIS, etc.")
    status: Literal["held", "completed", "void"] = Field("completed", description="Order status")
