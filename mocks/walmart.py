from copy import deepcopy

from .store import load_json, save_json


def get_state():
    return load_json("walmart_order.json")


def lookup_order(caller_phone=None):
    orders = load_json("walmart_order.json")
    return deepcopy(orders["order_1042"])


def propose_substitution(item_name="cereal", substitute_name=None):
    orders = load_json("walmart_order.json")
    order = orders["order_1042"]
    suggestion = _choose_suggestion(order, substitute_name)
    pending = {
        "from": "Honey Crunch Cereal",
        "to": suggestion["name"],
        "sku": suggestion["sku"],
        "price": suggestion["price"],
        "reason": suggestion["reason"],
        "status": "pending_confirmation",
    }
    order["pending_substitution"] = pending
    save_json("walmart_order.json", orders)
    return deepcopy({"order": order, "pending": pending})


def apply_pending_substitution():
    orders = load_json("walmart_order.json")
    order = orders["order_1042"]
    pending = order.get("pending_substitution")
    if not pending:
        return {"applied": False, "reason": "No pending substitution", "order": deepcopy(order)}
    for item in order["items"]:
        if item["name"] == pending["from"]:
            item["substitution"] = pending["to"]
            item["status"] = "substituted"
    order["pending_substitution"] = None
    order["status"] = "substitution_confirmed"
    save_json("walmart_order.json", orders)
    return {"applied": True, "substitution": deepcopy(pending), "order": deepcopy(order)}


def reset():
    orders = {
        "order_1042": {
            "id": "order_1042",
            "customer_phone": "+13185160977",
            "customer_name": "Alex",
            "store": "Walmart Supercenter - San Leandro",
            "status": "picking",
            "cutoff_status": "editable",
            "items": [
                {
                    "sku": "cereal_honey_crunch",
                    "name": "Honey Crunch Cereal",
                    "quantity": 1,
                    "status": "unavailable",
                    "substitution": None,
                },
                {
                    "sku": "milk_2_percent",
                    "name": "2% Milk",
                    "quantity": 1,
                    "status": "confirmed",
                    "substitution": None,
                },
            ],
            "suggestions": [
                {
                    "sku": "cereal_cinnamon_oat",
                    "name": "Cinnamon Oat Squares",
                    "price": 4.98,
                    "stock": 12,
                    "reason": "In stock and frequently purchased by this customer.",
                },
                {
                    "sku": "cereal_berry_granola",
                    "name": "Berry Granola",
                    "price": 5.42,
                    "stock": 5,
                    "reason": "Similar cereal category and available now.",
                },
            ],
            "pending_substitution": None,
        }
    }
    save_json("walmart_order.json", orders)
    return get_state()


def _choose_suggestion(order, substitute_name):
    if substitute_name:
        requested = " ".join(substitute_name.lower().split())
        for suggestion in order["suggestions"]:
            if requested in suggestion["name"].lower():
                return suggestion
    return order["suggestions"][0]
