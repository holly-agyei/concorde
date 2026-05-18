import asyncio
import os

from config import truthy
from events import push_event


def run_walmart_browser_task(task, caller_confirmed=False, force_browser=False, session_id=None):
    mode = os.getenv("WALMART_MODE", "mock").strip().lower()
    if mode != "browser" and not force_browser:
        return {
            "status": "skipped",
            "reason": "WALMART_MODE is mock",
            "message": "Using the local Walmart fallback panel.",
        }

    allow_save = truthy("BROWSER_USE_ALLOW_SAVE") and caller_confirmed
    guarded_task = _guarded_task(task, allow_save)

    if truthy("BROWSER_USE_DRY_RUN") or os.getenv("CONCORDE_OFFLINE_TESTS"):
        push_event(
            "browser_use_dry_run",
            {"task": guarded_task, "allow_save": allow_save, "session_id": session_id},
        )
        return {
            "status": "dry_run",
            "task": guarded_task,
            "allow_save": allow_save,
            "message": "Browser Use dry run; no live Walmart browser session was started.",
        }

    if not os.getenv("BROWSER_USE_API_KEY"):
        return {
            "status": "blocked",
            "reason": "BROWSER_USE_API_KEY is not configured",
            "message": "Browser Use is not configured, so the local Walmart fallback is active.",
        }

    push_event("browser_use_started", {"task": guarded_task, "allow_save": allow_save, "session_id": session_id})

    try:
        result = asyncio.run(_run_browser_use(guarded_task, session_id=session_id))
        push_event("browser_use_finished", {"output": result, "session_id": session_id})
        return {"status": "completed", "output": result, "allow_save": allow_save}
    except Exception as error:
        push_event("browser_use_failed", {"error": str(error)})
        return {
            "status": "blocked",
            "reason": str(error),
            "message": "Browser Use could not complete the Walmart workflow; using the fallback panel.",
        }


async def _run_browser_use(task, session_id=None):
    try:
        from browser_use_sdk.v3 import AsyncBrowserUse
    except Exception as error:
        raise RuntimeError(f"browser-use-sdk unavailable: {error}") from error

    client = AsyncBrowserUse(
        api_key=os.getenv("BROWSER_USE_API_KEY"),
        timeout=float(os.getenv("BROWSER_USE_HTTP_TIMEOUT", "60")),
    )
    kwargs = {"task": task}
    browser_session_id = os.getenv("BROWSER_USE_SESSION_ID")
    if browser_session_id:
        kwargs["session_id"] = browser_session_id
    profile_id = os.getenv("WALMART_BROWSER_PROFILE_ID")
    if profile_id:
        kwargs["profile_id"] = profile_id
    workspace_id = os.getenv("BROWSER_USE_WORKSPACE_ID")
    if workspace_id:
        kwargs["workspace_id"] = workspace_id
    model = os.getenv("BROWSER_USE_MODEL")
    if model:
        kwargs["model"] = model
    max_cost = os.getenv("BROWSER_USE_MAX_COST_USD")
    if max_cost:
        kwargs["max_cost_usd"] = float(max_cost)
    sensitive_data = _sensitive_data()
    if sensitive_data:
        kwargs["sensitive_data"] = sensitive_data
    kwargs["keep_alive"] = truthy("BROWSER_USE_KEEP_ALIVE", True)
    kwargs["enable_recording"] = truthy("BROWSER_USE_ENABLE_RECORDING", True)
    result = await client.run(**kwargs)
    return getattr(result, "output", str(result))


def _guarded_task(task, allow_save):
    base = (
        "Open Walmart.com using the configured Browser Use profile for the user's own account. "
        "Use the live Walmart account state, active orders, purchase history, and editable order pages. "
        "If login, 2FA, CAPTCHA, or account access blocks progress, stop and report the blocker. "
        "Do not expose personal account details beyond the task result. "
        "Do not buy anything, cancel anything, submit payment, refund anything, or save irreversible changes. "
    )
    if allow_save:
        base += (
            "The caller explicitly confirmed and the server permits saving. "
            "Save only the requested Walmart order change if Walmart shows a safe final confirmation. "
        )
    else:
        base += "Stop before the final save/apply/submit button and report exactly what would be changed. "
    return base + task


def _sensitive_data():
    values = {}
    for name in ["WALMART_EMAIL", "WALMART_PASSWORD", "WALMART_PHONE", "WALMART_ZIP_CODE"]:
        value = os.getenv(name)
        if value:
            values[name] = value
    return values

