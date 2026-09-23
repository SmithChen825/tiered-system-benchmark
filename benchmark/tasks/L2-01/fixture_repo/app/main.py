from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

ITEMS = {
    1: {"id": 1, "name": "Aurora Lamp", "category": "Lighting", "price": 79.0},
    2: {"id": 2, "name": "Harbor Pack", "category": "Carry", "price": 129.0},
    3: {"id": 3, "name": "Mesa Mug", "category": "Drinkware", "price": 24.0},
}

def create_app() -> FastAPI:
    application = FastAPI(title="Northstar Items")

    @application.get("/health")
    def health() -> dict[str, str]: return {"status": "ok"}

    @application.get("/", response_class=HTMLResponse)
    def item_index() -> str:
        links = "".join(f'<li><a href="/items/{item["id"]}">{item["name"]}</a></li>' for item in ITEMS.values())
        return f"<!doctype html><title>Items</title><main><h1>Items</h1><ul>{links}</ul></main>"

    @application.get("/api/items/{item_id}")
    def item_api(item_id: int) -> dict[str, object]:
        item = ITEMS.get(item_id)
        if item is None: raise HTTPException(status_code=404, detail="Item not found")
        return item

    @application.get("/items/{item_id}", response_class=HTMLResponse)
    def item_detail(product_id: int) -> str:
        item = ITEMS.get(product_id)
        if item is None: raise HTTPException(status_code=404, detail="Item not found")
        return f'<!doctype html><title>{item["name"]}</title><main data-testid="item-detail"><h1>{item["name"]}</h1><p>{item["category"]}</p><data value="{item["price"]:.2f}">${item["price"]:.2f}</data></main>'

    return application

app = create_app()
