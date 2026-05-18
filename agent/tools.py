from events import push_event
from integrations.browser_walmart import run_walmart_browser_task
from integrations.doordash_browser import run_doordash_browser_task
from integrations.moss_runtime import semantic_lookup as moss_lookup
from mocks import uber, walmart


def lookup_uber_trip(caller_phone=None):
    result = uber.lookup_trip(caller_phone)
    push_event("uber_trip_lookup", {"customer": result["customer"]["name"], "ride_id": result["ride"]["id"]})
    return result


def reroute_uber_driver(destination_label):
    result = uber.reroute_driver(destination_label)
    push_event(
        "uber_rerouted",
        {
            "from": result["previous"]["label"],
            "to": result["destination"]["label"],
            "door": result["destination"].get("door"),
            "eta_minutes": result["eta_minutes"],
            "distance_miles": result["distance_miles"],
        },
    )
    push_event(
        "driver_notified",
        {"message": f"Pickup updated to {result['destination']['label']} {result['destination'].get('door', '')}".strip()},
    )
    return result


def lookup_walmart_order(caller_phone=None):
    result = walmart.lookup_order(caller_phone)
    push_event("walmart_order_lookup", {"order_id": result["id"], "status": result["status"]})
    return result


def propose_walmart_substitution(item_name="cereal", substitute_name=None):
    result = walmart.propose_substitution(item_name, substitute_name)
    push_event(
        "walmart_substitution_proposed",
        {
            "from": result["pending"]["from"],
            "to": result["pending"]["to"],
            "reason": result["pending"]["reason"],
        },
    )
    return result


def apply_walmart_substitution():
    result = walmart.apply_pending_substitution()
    if result.get("applied"):
        push_event(
            "walmart_substitution_applied",
            {"from": result["substitution"]["from"], "to": result["substitution"]["to"]},
        )
    else:
        push_event("walmart_substitution_failed", {"reason": result.get("reason")})
    return result


def semantic_lookup(query):
    return moss_lookup(query)


def walmart_browser_task(task, caller_confirmed=False):
    return run_walmart_browser_task(task, caller_confirmed=caller_confirmed)


def doordash_browser_task(task, action="add", search_term="", remove_query=""):
    plan = {
        "action": action,
        "search_term": search_term,
        "remove_query": remove_query,
        "browser_task": task,
    }
    return run_doordash_browser_task(task, plan=plan)


TOOL_REGISTRY = {
    "lookup_uber_trip": lambda args, ctx: lookup_uber_trip(ctx.get("caller_phone")),
    "reroute_uber_driver": lambda args, ctx: reroute_uber_driver(args.get("destination_label")),
    "lookup_walmart_order": lambda args, ctx: lookup_walmart_order(ctx.get("caller_phone")),
    "propose_walmart_substitution": lambda args, ctx: propose_walmart_substitution(
        args.get("item_name", "cereal"), args.get("substitute_name")
    ),
    "apply_walmart_substitution": lambda args, ctx: apply_walmart_substitution(),
    "run_walmart_browser_task": lambda args, ctx: walmart_browser_task(
        args.get("task", "Open Walmart purchase history and inspect substitution options."),
        caller_confirmed=bool(args.get("caller_confirmed")),
    ),
    "run_doordash_browser_task": lambda args, ctx: doordash_browser_task(
        args.get("task", "Open DoorDash and handle the user's safe cart request."),
        action=args.get("action", "add"),
        search_term=args.get("search_term", ""),
        remove_query=args.get("remove_query", ""),
    ),
    "semantic_lookup": lambda args, ctx: semantic_lookup(args.get("query", "")),
}
