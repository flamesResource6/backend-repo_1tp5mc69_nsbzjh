import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Menuitem, Order, OrderItem

app = FastAPI(title="FoodKasir API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"name": "FoodKasir API", "status": "ok"}

# Health + DB test
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# Helper to convert Mongo docs

def serialize_doc(doc):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc

# ---------------------- Admin & Menu ----------------------
# Seed minimal menu if empty
@app.post("/api/admin/seed")
def seed_menu():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    count = db["menuitem"].count_documents({})
    if count > 0:
        return {"seeded": False, "count": count}
    items = [
        {"name": "Nasi Goreng", "category": "Food", "price": 18000.0, "is_active": True},
        {"name": "Mie Ayam", "category": "Food", "price": 15000.0, "is_active": True},
        {"name": "Es Teh Manis", "category": "Drink", "price": 5000.0, "is_active": True},
        {"name": "Kopi Hitam", "category": "Drink", "price": 8000.0, "is_active": True},
    ]
    for it in items:
        create_document("menuitem", it)
    return {"seeded": True, "count": len(items)}

# Public: list active menu
@app.get("/api/menu")
def list_menu():
    docs = get_documents("menuitem", {"is_active": True})
    return [serialize_doc(d) for d in docs]

# Admin: list all menu items
@app.get("/api/admin/menu")
def admin_list_menu():
    docs = get_documents("menuitem", {})
    return [serialize_doc(d) for d in docs]

# Admin: add or update menu
class MenuUpsert(BaseModel):
    id: str | None = None
    name: str
    category: str | None = None
    price: float
    image_url: str | None = None
    is_active: bool = True

@app.post("/api/admin/menu")
def upsert_menu(item: MenuUpsert):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = item.model_dump()
    _id = data.pop("id", None)
    if _id:
        try:
            oid = ObjectId(_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")
        result = db["menuitem"].find_one_and_update(
            {"_id": oid}, {"$set": data}
        )
        if not result:
            raise HTTPException(status_code=404, detail="Menu item not found")
        return {"updated": True}
    else:
        new_id = create_document("menuitem", data)
        return {"created": True, "id": new_id}

# Admin: toggle active or delete item
@app.delete("/api/admin/menu/{item_id}")
def delete_menu_item(item_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    res = db["menuitem"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return {"deleted": True}

# ---------------------- Orders ----------------------
@app.post("/api/orders")
def create_order(order: Order):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # Basic validation of subtotals
    total_calc = 0.0
    for it in order.items:
        expected = round(it.price * it.quantity, 2)
        if round(it.subtotal, 2) != expected:
            raise HTTPException(status_code=400, detail=f"Invalid subtotal for {it.name}")
        total_calc += expected
    if round(order.total, 2) != round(total_calc, 2):
        raise HTTPException(status_code=400, detail="Total mismatch")

    payload = order.model_dump()
    # default status if not provided by client
    if "status" not in payload or payload["status"] is None:
        payload["status"] = "completed"
    order_id = create_document("order", payload)
    return {"id": order_id}

# Update order status: held, completed, void
class OrderStatusUpdate(BaseModel):
    status: Literal["held", "completed", "void"]

@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: str, body: OrderStatusUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    result = db["order"].find_one_and_update(
        {"_id": oid}, {"$set": {"status": body.status}}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"updated": True}

# Get recent orders (optionally by status)
@app.get("/api/history")
def sales_history(limit: int = 50, status: str | None = None):
    query = {}
    if status:
        query["status"] = status
    docs = get_documents("order", query, limit)
    return [serialize_doc(d) for d in docs]

# Fetch single order (e.g., resume held)
@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = db["order"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_doc(doc)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
