from copy import deepcopy

from .store import load_json, save_json


_TERMINAL_1 = {
    "lat": 37.615002,
    "lng": -122.384530,
    "label": "SFO Terminal 1",
    "door": "Door 1",
    "eta_minutes": 9,
    "distance_miles": 2.8,
}

_TERMINAL_2 = {
    "lat": 37.617306,
    "lng": -122.383940,
    "label": "SFO Terminal 2",
    "door": "Door 2",
    "eta_minutes": 6,
    "distance_miles": 1.1,
}

_TERMINAL_3 = {
    "lat": 37.617790,
    "lng": -122.387639,
    "label": "SFO Terminal 3",
    "door": "Door 3",
    "eta_minutes": 8,
    "distance_miles": 1.6,
}

_INTERNATIONAL = {
    "lat": 37.615939,
    "lng": -122.388910,
    "label": "SFO International Terminal",
    "door": "Door G",
    "eta_minutes": 11,
    "distance_miles": 3.4,
}

KNOWN_DESTINATIONS = {
    "sfo terminal 1": _TERMINAL_1,
    "terminal 1": _TERMINAL_1,
    "harvey milk terminal 1": _TERMINAL_1,
    "harvey milk terminal": _TERMINAL_1,
    "sfo terminal 2": _TERMINAL_2,
    "terminal 2": _TERMINAL_2,
    "sfo terminal 3": _TERMINAL_3,
    "terminal 3": _TERMINAL_3,
    "sfo international terminal": _INTERNATIONAL,
    "international terminal": _INTERNATIONAL,
    "intl terminal": _INTERNATIONAL,
    "international": _INTERNATIONAL,
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
    if "terminal 1" in normalized or "harvey milk" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo terminal 1"])
    if "terminal 2" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo terminal 2"])
    if "terminal 3" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo terminal 3"])
    if "international" in normalized or "intl" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["sfo international terminal"])
    if "tower 2" in normalized:
        return deepcopy(KNOWN_DESTINATIONS["salesforce tower 2"])
    return {
        "lat": 37.617306,
        "lng": -122.383940,
        "label": str(label or "SFO Terminal 2"),
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

    if previous and previous.get("label") == destination["label"]:
        return {
            "previous": previous,
            "destination": deepcopy(driver["destination"]),
            "eta_minutes": driver.get("eta_minutes"),
            "distance_miles": driver.get("distance_miles"),
            "driver": deepcopy(driver),
            "ride": deepcopy(ride),
            "unchanged": True,
        }

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
            "name": "David",
            "phone": "+14155550199",
            "current_location": {"lat": 37.6213, "lng": -122.3790, "label": "SFO approach"},
            "destination": {"lat": 37.617306, "lng": -122.383940, "label": "SFO Terminal 2", "door": "Door 2"},
            "status": "en_route",
            "eta_minutes": 6,
            "distance_miles": 1.1,
        }
    }
    rides = {
        "ride_001": {
            "id": "ride_001",
            "customer_phone": "+13185160977",
            "customer_name": "Alex",
            "driver_id": "driver_001",
            "service": "UberX",
            "pickup": {"lat": 37.629477, "lng": -122.414823, "label": "450 San Bruno Avenue W"},
            "destination": {"lat": 37.617306, "lng": -122.383940, "label": "SFO Terminal 2", "door": "Door 2"},
            "status": "in_progress",
            "rating": "4.9",
        }
    }
    save_json("drivers.json", drivers)
    save_json("rides.json", rides)
    return get_state()
