from copy import deepcopy

from .store import load_json, save_json


KNOWN_DESTINATIONS = {
    "sfo terminal c": {
        "lat": 37.6190,
        "lng": -122.3830,
        "label": "SFO Terminal C",
        "door": "Door 3",
        "eta_minutes": 12,
        "distance_miles": 4.3,
    },
    "terminal c": {
        "lat": 37.6190,
        "lng": -122.3830,
        "label": "SFO Terminal C",
        "door": "Door 3",
        "eta_minutes": 12,
        "distance_miles": 4.3,
    },
    "sfo terminal d": {
        "lat": 37.6177,
        "lng": -122.3864,
        "label": "SFO Terminal D",
        "door": "Door 5",
        "eta_minutes": 6,
        "distance_miles": 1.1,
    },
    "terminal d": {
        "lat": 37.6177,
        "lng": -122.3864,
        "label": "SFO Terminal D",
        "door": "Door 5",
        "eta_minutes": 6,
        "distance_miles": 1.1,
    },
    "salesforce tower 2": {
        "lat": 37.7890,
        "lng": -122.3969,
        "label": "Salesforce Tower 2",
        "door": "Main lobby",
        "eta_minutes": 4,
        "distance_miles": 0.2,
    },
}


def _normalize_phone(phone):
    if not phone:
        return "+13185160977"
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return str(phone)


def _resolve_destination(label):
    normalized = " ".join(str(label or "").lower().split())
    if normalized in KNOWN_DESTINATIONS:
        return deepcopy(KNOWN_DESTINATIONS[normalized])
    if "terminal d" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo terminal d"])
    if "terminal c" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo terminal c"])
    if "tower 2" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["salesforce tower 2"])
    return {
        "lat": 37.6190,
        "lng": -122.3830,
        "label": str(label or "SFO Terminal C"),
        "door": "Confirm with rider",
        "eta_minutes": 10,
        "distance_miles": 2.0,
    }


def get_state():
    customers = load_json("customers.json")
    rides = load_json("rides.json")
    drivers = load_json("drivers.json")
    return {"customers": customers, "rides": rides, "drivers": drivers}


def lookup_trip(caller_phone):
    phone = _normalize_phone(caller_phone)
    customers = load_json("customers.json")
    customer = customers.get(phone) or customers.get("+13185160977")
    rides = load_json("rides.json")
    drivers = load_json("drivers.json")
    ride = rides.get(customer["active_ride_id"])
    driver = drivers.get(ride["driver_id"])
    return {
        "customer": deepcopy(customer),
        "ride": deepcopy(ride),
        "driver": deepcopy(driver),
    }


def reroute_driver(destination_label):
    destination = _resolve_destination(destination_label)
    rides = load_json("rides.json")
    drivers = load_json("drivers.json")
    ride = rides["ride_001"]
    driver = drivers[ride["driver_id"]]
    previous = deepcopy(driver["destination"])

    driver["destination"] = {
        "lat": destination["lat"],
        "lng": destination["lng"],
        "label": destination["label"],
        "door": destination["door"],
    }
    driver["eta_minutes"] = destination["eta_minutes"]
    driver["distance_miles"] = destination["distance_miles"]
    ride["destination"] = deepcopy(driver["destination"])

    save_json("drivers.json", drivers)
    save_json("rides.json", rides)
    return {
        "previous": previous,
        "destination": deepcopy(driver["destination"]),
        "eta_minutes": driver["eta_minutes"],
        "distance_miles": driver["distance_miles"],
        "driver": deepcopy(driver),
        "ride": deepcopy(ride),
    }


def reset():
    drivers = {
        "driver_001": {
            "id": "driver_001",
            "name": "Marcus",
            "phone": "+14155550199",
            "current_location": {"lat": 37.6213, "lng": -122.3790, "label": "SFO approach"},
            "destination": {"lat": 37.6190, "lng": -122.3830, "label": "SFO Terminal C", "door": "Door 3"},
            "status": "en_route",
            "eta_minutes": 12,
            "distance_miles": 4.3,
        }
    }
    rides = {
        "ride_001": {
            "id": "ride_001",
            "customer_phone": "+13185160977",
            "customer_name": "Alex",
            "driver_id": "driver_001",
            "service": "UberX",
            "pickup": {"lat": 37.7936, "lng": -122.3956, "label": "152 Mission St"},
            "destination": {"lat": 37.6190, "lng": -122.3830, "label": "SFO Terminal C", "door": "Door 3"},
            "status": "in_progress",
            "rating": "4.9",
        }
    }
    save_json("drivers.json", drivers)
    save_json("rides.json", rides)
    return get_state()
