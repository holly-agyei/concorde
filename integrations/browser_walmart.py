import asyncio
import os

from config import truthy
from events import push_event


def run_walmart_browser_task(task, caller_confirmed=False):
    mode = os.getenv("WALMART_MODE", "mock").strip().lower()
    if mode != "browser":
        return {
            "status": "skipped",
            "reason": "WALMART_MODE is mock",
            "message": "Using the local Walmart fallback panel.",
        }

    if not os.getenv("BROWSER_USE_API_KEY"):
        return {
            "status": "blocked",
            "reason": "BROWSER_USE_API_KEY is not configured",
            "message": "Browser Use is not configured, so the local Walmart fallback is active.",
        }

    allow_save = truthy("BROWSER_USE_ALLOW_SAVE") and caller_confirmed
    guarded_task = _guarded_task(task, allow_save)
    push_event("browser_use_started", {"task": guarded_task, "allow_save": allow_save})

    try:
        result = asyncio.run(_run_browser_use(guarded_task))
        push_event("browser_use_finished", {"output": result})
        return {"status": "completed", "output": result, "allow_save": allow_save}
    except Exception as error:
        push_event("browser_use_failed", {"error": str(error)})
        return {
            "status": "blocked",
            "reason": str(error),
            "message": "Browser Use could not complete the Walmart workflow; using the fallback panel.",
        }


async def _run_browser_use(task):
    try:
        from browser_use_sdk.v3 import AsyncBrowserUse
    except Exception as error:
        raise RuntimeError(f"browser-use-sdk unavailable: {error}") from error

    client = AsyncBrowserUse()
    kwargs = {"task": task}
    profile_id = os.getenv("WALMART_BROWSER_PROFILE_ID")
    if profile_id:
        kwargs["profile_id"] = profile_id
    result = await client.run(**kwargs)
    return getattr(result, "output", str(result))


def _guarded_task(task, allow_save):
    base = (
        "Go to Walmart.com purchase history for the logged-in user. "
        "Find the editable grocery order related to cereal substitutions. "
        "Do not buy anything, cancel anything, submit payment, or save irreversible changes. "
    )
    if allow_save:
        base += "The caller explicitly confirmed the substitution, so save only that substitution if Walmart shows a safe final confirmation. "
    else:
        base += "Stop before the final save/apply button and report exactly what would be changed. "
    return base + task
