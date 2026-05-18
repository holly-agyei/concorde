import json
import os
import re
import subprocess
import time
from pathlib import Path

from config import truthy
from events import push_event


ROOT = Path(__file__).resolve().parents[1]
DOORDASH_URL = "https://www.doordash.com/"
SAFE_ACTIONS = {"add", "remove", "replace", "view_cart", "search", "open"}

DEFAULT_CHROME_PROFILE = ROOT / "data" / "chrome-profile"
CDP_PORT = int(os.getenv("DOORDASH_CDP_PORT", "9222"))
CHROME_APP_MACOS = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_CHECKOUT_TEXT = re.compile(
    r"\b(checkout|check\s*out|place\s+order|place\s+this\s+order|submit\s+order|"
    r"complete\s+order|pay\b|buy\b|purchase\b|subscribe|dashpass)\b",
    re.IGNORECASE,
)


def _chrome_profile_dir():
    configured = os.getenv("DOORDASH_CHROME_PROFILE_DIR", str(DEFAULT_CHROME_PROFILE))
    path = Path(configured)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _chrome_binary():
    return os.getenv("DOORDASH_CHROME_BINARY", CHROME_APP_MACOS)


def _cdp_url():
    return f"http://127.0.0.1:{CDP_PORT}"


def _is_cdp_alive(timeout=1.0):
    import urllib.request
    try:
        with urllib.request.urlopen(f"{_cdp_url()}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _launch_real_chrome_with_cdp(start_url=DOORDASH_URL):
    profile = _chrome_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [
        _chrome_binary(),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        start_url,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_cdp(timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_cdp_alive():
            return True
        time.sleep(0.4)
    return False


def _profile_dir_ready(path):
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except Exception:
        return False


def run_doordash_browser_task(task, session_id=None, plan=None):
    plan = _coerce_plan(plan)
    guarded_task = _guarded_task(task, plan)
    if truthy("DOORDASH_DRY_RUN") or os.getenv("CONCORDE_OFFLINE_TESTS"):
        push_event("doordash_browser_dry_run", {"task": guarded_task, "session_id": session_id, "plan": plan})
        return {
            "status": "dry_run",
            "task": guarded_task,
            "plan": plan,
            "message": "DoorDash dry run; no browser was opened.",
        }

    push_event("doordash_browser_started", {"task": guarded_task, "session_id": session_id, "plan": plan})
    try:
        result = _run_visible_chrome(guarded_task, plan, session_id=session_id)
        push_event("doordash_browser_finished", {"result": result, "session_id": session_id})
        status = result.pop("_status", "completed")
        return {"status": status, "plan": plan, **result}
    except Exception as error:
        push_event("doordash_browser_failed", {"error": str(error), "session_id": session_id})
        return {
            "status": "blocked",
            "plan": plan,
            "reason": str(error),
            "message": "DoorDash browser automation could not complete.",
        }


def _run_visible_chrome(task, plan, session_id=None):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(f"playwright unavailable: {error}") from error

    profile_dir = _chrome_profile_dir()
    action = plan["action"]
    search_term = plan.get("search_term", "")
    remove_query = plan.get("remove_query", "")

    if not _profile_dir_ready(profile_dir):
        return {
            "_status": "blocked",
            "output": "No saved DoorDash login. Run `python3 scripts/login_doordash.py` first to log in.",
            "action": action,
            "search_term": search_term,
            "remove_query": remove_query,
            "url": DOORDASH_URL,
            "cart_changed": False,
        }

    needs_search = action in {"add", "search", "replace"}
    if needs_search and not search_term:
        return {
            "_status": "blocked",
            "output": "I need a specific item or restaurant name to search DoorDash. Please tell me what to add.",
            "action": action,
            "search_term": search_term,
            "remove_query": remove_query,
            "url": DOORDASH_URL,
            "cart_changed": False,
        }

    if not _is_cdp_alive():
        try:
            _launch_real_chrome_with_cdp(DOORDASH_URL)
        except Exception as error:
            return {
                "_status": "blocked",
                "output": f"Could not start Chrome for DoorDash automation. ({error})",
                "action": action,
                "search_term": search_term,
                "remove_query": remove_query,
                "url": DOORDASH_URL,
                "cart_changed": False,
            }
        if not _wait_for_cdp(timeout=20):
            return {
                "_status": "blocked",
                "output": "Could not start Chrome for DoorDash automation.",
                "action": action,
                "search_term": search_term,
                "remove_query": remove_query,
                "url": DOORDASH_URL,
                "cart_changed": False,
            }

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(_cdp_url())
        except PlaywrightError as error:
            return {
                "_status": "blocked",
                "output": f"Could not connect to Chrome over CDP: {error}",
                "action": action,
                "search_term": search_term,
                "remove_query": remove_query,
                "url": DOORDASH_URL,
                "cart_changed": False,
            }

        page = None
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _grab_or_open_doordash_tab(context)

            try:
                page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass

            blocker = _visible_blocker(page)
            if blocker:
                return {
                    "_status": "blocked",
                    "output": blocker,
                    "action": action,
                    "search_term": search_term,
                    "remove_query": remove_query,
                    "url": page.url,
                    "cart_changed": False,
                }

            log = [f"Opened DoorDash in your real Chrome (profile {profile_dir.name})."]

            cart_changed = False
            added = False
            removed = False

            if action in {"view_cart", "remove", "replace"}:
                log.extend(_open_cart(page, PlaywrightTimeoutError))

            if action == "view_cart":
                cart_count = _cart_count(page)
                log.append(f"Cart currently shows {cart_count} item(s).")

            elif action == "remove":
                removed = _try_remove_from_cart(page, remove_query, PlaywrightTimeoutError)
                cart_changed = removed
                cart_count = _cart_count(page)
                if removed:
                    target = f" matching '{remove_query}'" if remove_query else ""
                    log.append(f"Removed one cart item{target}. Cart now shows {cart_count} item(s).")
                else:
                    log.append("I opened the cart but could not find a removable matching item.")

            elif action == "replace":
                removed = _try_remove_from_cart(page, remove_query, PlaywrightTimeoutError)
                if removed:
                    target = f" matching '{remove_query}'" if remove_query else ""
                    log.append(f"Removed one cart item{target}.")
                else:
                    log.append("I could not safely remove the existing item, so I did not add a replacement.")
                if removed and search_term:
                    page.goto(DOORDASH_URL, wait_until="domcontentloaded", timeout=20000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=2000)
                    except Exception:
                        pass
                    log.extend(_open_search_results(page, search_term, PlaywrightTimeoutError))
                    added = _try_prepare_cart(page, PlaywrightTimeoutError)
                    cart_changed = added
                    cart_count = _cart_count(page)
                    if added:
                        log.append(f"Added a replacement for {search_term}. Cart now shows {cart_count} item(s).")
                    else:
                        log.append(f"I searched for {search_term} but could not safely add a replacement.")
                else:
                    cart_count = _cart_count(page)

            elif action in {"add", "search"}:
                log.extend(_open_search_results(page, search_term, PlaywrightTimeoutError))
                if action == "add":
                    before = _cart_count(page)
                    added = _try_prepare_cart(page, PlaywrightTimeoutError)
                    cart_count = _cart_count(page)
                    cart_changed = added
                    if added:
                        log.append(f"Added {search_term} to cart and stopped before checkout. Cart now shows {cart_count} item(s).")
                    else:
                        log.append(f"Stopped before checkout. Cart was {before} item(s); could not safely add {search_term}.")
                else:
                    cart_count = _cart_count(page)
                    log.append(f"Searched DoorDash for {search_term} and stopped without cart changes.")

            else:  # open
                cart_count = _cart_count(page)
                log.append("Opened DoorDash and stopped without cart changes.")

            return {
                "_status": "completed",
                "output": " ".join(log),
                "action": action,
                "search_term": search_term,
                "remove_query": remove_query,
                "url": page.url,
                "cart_changed": cart_changed,
                "cart_count": cart_count,
                "added": added,
                "removed": removed,
            }
        finally:
            if page is not None and truthy("DOORDASH_KEEP_BROWSER_OPEN", True):
                try:
                    page.wait_for_timeout(int(os.getenv("DOORDASH_BROWSER_HOLD_MS", "3000")))
                except Exception:
                    pass
            # Never close browser/context — it's the user's real Chrome.


# ----------------------------------------------------------------------------
# Tab management — reuse one DoorDash tab, close stale duplicates
# ----------------------------------------------------------------------------

def _grab_or_open_doordash_tab(context):
    doordash_pages = [p for p in context.pages if _is_doordash_url(p.url)]
    if doordash_pages:
        # Keep the newest, close the rest to prevent tab accumulation
        keeper = doordash_pages[-1]
        for stale in doordash_pages[:-1]:
            try:
                stale.close()
            except Exception:
                pass
        try:
            keeper.bring_to_front()
        except Exception:
            pass
        # Refresh to home so each task starts from a known state
        try:
            keeper.goto(DOORDASH_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        return keeper
    # No DoorDash tab open — open one
    page = context.new_page()
    page.goto(DOORDASH_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        page.bring_to_front()
    except Exception:
        pass
    return page


def _is_doordash_url(url):
    return bool(url) and "doordash.com" in url


# ----------------------------------------------------------------------------
# Action helpers
# ----------------------------------------------------------------------------

def _open_search_results(page, search_term, timeout_error):
    logs = _try_search(page, search_term, timeout_error)
    try:
        page.wait_for_load_state("networkidle", timeout=2500)
    except Exception:
        pass
    if "/search/" in (page.url or ""):
        return logs
    # Fall back to direct search URL
    try:
        page.goto(
            f"https://www.doordash.com/search/store/{search_term}?suggestion_type=cuisine",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass
        return logs + [f"Opened DoorDash search results for {search_term}."]
    except Exception as error:
        return logs + [f"Search navigation failed: {error}"]


def _try_search(page, search_term, timeout_error):
    locators = [
        page.get_by_role("textbox", name=re.compile("search|restaurant|dish|store|item", re.I)),
        page.locator("input[type='search']"),
        page.locator("input[placeholder*='Search' i]"),
    ]
    for locator in locators:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=2500)
            target.fill(search_term)
            target.press("Enter")
            return [f"Searched DoorDash for {search_term}."]
        except timeout_error:
            continue
        except Exception:
            continue
    return [f"No visible search box found; falling back to direct search URL for {search_term}."]


def _open_cart(page, timeout_error):
    candidates = [
        page.get_by_label(re.compile(r"open order cart|cart|items?.*cart", re.I)),
        page.get_by_role("button", name=re.compile(r"cart|view cart|open order", re.I)),
        page.get_by_text(re.compile(r"view cart|cart", re.I)),
    ]
    for locator in candidates:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=3000)
            target.click()
            try:
                page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass
            return ["Opened the DoorDash cart."]
        except timeout_error:
            continue
        except Exception:
            continue
    return ["I could not find a cart button on the current page."]


def _try_prepare_cart(page, timeout_error):
    store_href = _first_store_href(page)
    if store_href:
        try:
            page.goto(store_href, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            try:
                page.wait_for_timeout(2500)
            except Exception:
                pass
        except Exception:
            pass

    # Try clicking common "Featured Items" tab if visible
    try:
        page.get_by_label("Featured Items").click(timeout=3000)
        page.wait_for_timeout(1200)
    except Exception:
        pass

    before = _cart_count(page)

    # Strategy 1: click the visible "Add" icon on a menu item card
    if _click_visible_add_icon(page):
        try:
            page.wait_for_timeout(2500)
        except Exception:
            pass
        if _cart_count(page) > before:
            return True
        # Sometimes opens a customization modal that needs "Add to cart"
        if _click_modal_add_button(page):
            try:
                page.wait_for_timeout(2500)
            except Exception:
                pass
            return _cart_count(page) > before

    # Strategy 2: explicit role-based "Add" button
    candidates = [
        page.get_by_role("button", name=re.compile(r"^add(?!ress)|add to cart|add item", re.I)),
        page.get_by_text(re.compile(r"^add(?!ress)|add to cart|add item", re.I)),
    ]
    for locator in candidates:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=2500)
            target.click()
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
            return _cart_count(page) > before
        except timeout_error:
            continue
        except Exception:
            continue

    # Strategy 3: open the first menu item and click "Add to cart" in modal
    if _click_first_menu_item(page):
        try:
            page.wait_for_timeout(1800)
        except Exception:
            pass
        if _click_modal_add_button(page):
            try:
                page.wait_for_timeout(2500)
            except Exception:
                pass
            return _cart_count(page) > before
    return False


def _try_remove_from_cart(page, remove_query, timeout_error):
    before = _cart_count(page)
    if _click_matching_cart_remove(page, remove_query):
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass
        _confirm_cart_mutation(page, timeout_error)
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass
        return _cart_count(page) < before or before == 0

    for pattern in [r"remove", r"delete", r"decrease", r"minus", r"^-$"]:
        try:
            page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(timeout=2000)
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
            _confirm_cart_mutation(page, timeout_error)
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
            return _cart_count(page) < before or before == 0
        except timeout_error:
            continue
        except Exception:
            continue
    return False


def _click_matching_cart_remove(page, remove_query):
    try:
        return page.locator("body").evaluate(
            """query => {
                const normalizedQuery = String(query || '').toLowerCase().trim();
                const words = normalizedQuery.split(/\\s+/).filter(Boolean);
                const visible = el => {
                  const rect = el.getBoundingClientRect();
                  const style = window.getComputedStyle(el);
                  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const textOf = el => (el.innerText || el.textContent || '').toLowerCase();
                const containers = Array.from(document.querySelectorAll('article, li, [data-testid], div'))
                  .filter(el => visible(el) && textOf(el).length > 0 && textOf(el).length < 1200);
                const container = words.length
                  ? containers.find(el => words.every(word => textOf(el).includes(word)))
                  : containers.find(el => /cart|order|subtotal/.test(textOf(el)));
                if (!container) return false;
                const buttons = Array.from(container.querySelectorAll('button, [role="button"]')).filter(visible);
                const remove = buttons.find(btn => {
                  const label = [
                    btn.getAttribute('aria-label'),
                    btn.getAttribute('title'),
                    btn.innerText,
                    btn.textContent
                  ].join(' ').toLowerCase();
                  return /remove|delete|decrease|minus|subtract|^\\s*[-−]\\s*$/.test(label);
                });
                if (!remove) return false;
                remove.click();
                return true;
            }""",
            remove_query or "",
        )
    except Exception:
        return False


def _confirm_cart_mutation(page, timeout_error):
    for pattern in [r"remove", r"delete", r"update cart", r"save changes", r"done"]:
        try:
            page.get_by_role("button", name=re.compile(pattern, re.I)).last.click(timeout=2000)
            return True
        except timeout_error:
            continue
        except Exception:
            continue
    return False


def _first_store_href(page):
    try:
        return page.locator("a[href*='/store/']").evaluate_all(
            """els => {
                const target = els.find((anchor) => {
                    const rect = anchor.getBoundingClientRect();
                    return rect.x > 150 && rect.y > 100 && rect.width > 100 && rect.height > 80;
                });
                return target ? target.href : null;
            }"""
        )
    except Exception:
        return None


def _click_visible_add_icon(page):
    try:
        buttons = page.get_by_label("Add item to cart")
        count = buttons.count()
    except Exception:
        return False
    for index in range(count):
        button = buttons.nth(index)
        try:
            box = button.bounding_box(timeout=1000)
            if box and box["x"] > 150 and 60 < box["y"] < 900:
                # SAFETY: refuse if the button's accessible text reads like checkout
                try:
                    label = button.get_attribute("aria-label", timeout=500) or ""
                except Exception:
                    label = ""
                if _CHECKOUT_TEXT.search(label):
                    continue
                button.click(timeout=4000)
                return True
        except Exception:
            continue
    return False


def _click_first_menu_item(page):
    try:
        return page.locator("body").evaluate(
            """() => {
                const visible = el => {
                  const rect = el.getBoundingClientRect();
                  const style = window.getComputedStyle(el);
                  return rect.width > 120 && rect.height > 45 && rect.y > 100 && rect.y < 900 &&
                    rect.x > 150 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const textOf = el => (el.innerText || el.textContent || '').trim();
                const badText = /checkout|subtotal|delivery fee|dasher|sign in|address|cart|privacy|terms|pay|dashpass/i;
                const selectors = [
                  '[data-testid*="MenuItem"]',
                  '[data-anchor-id*="MenuItem"]',
                  'button',
                  '[role="button"]',
                  'article',
                  'a'
                ];
                const candidates = selectors.flatMap(sel => Array.from(document.querySelectorAll(sel)));
                const target = candidates.find(el => {
                  const text = textOf(el);
                  return visible(el) && text.length > 8 && text.length < 400 && !badText.test(text);
                });
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
    except Exception:
        return False


def _click_modal_add_button(page):
    # Locate the modal dialog (DoorDash's customization popup)
    dialog = None
    try:
        candidate = page.get_by_role("dialog").first
        candidate.wait_for(state="visible", timeout=2000)
        dialog = candidate
    except Exception:
        dialog = None

    scope = dialog if dialog is not None else page

    # Step 1: scroll the modal to the TOP so required sections are in view.
    # DoorDash often opens the modal scrolled down past the size choices.
    try:
        page.evaluate(
            """() => {
                const modal = document.querySelector('[role="dialog"], [aria-modal="true"]');
                if (!modal) return;
                modal.scrollTop = 0;
                const scrollables = modal.querySelectorAll('*');
                for (const el of scrollables) {
                    try {
                        if (el.scrollHeight > el.clientHeight + 4) el.scrollTop = 0;
                    } catch (e) {}
                }
            }"""
        )
        page.wait_for_timeout(300)
    except Exception:
        pass

    # Step 2: satisfy required radio groups using Playwright locators (these
    # auto-scroll-into-view before clicking, which JS .click() does not).
    _select_first_radio_per_group(scope, page)

    # Wait for the CTA text to refresh after selections
    try:
        page.wait_for_timeout(600)
    except Exception:
        pass

    # Step 3: click the bottom-of-modal "Add to cart" CTA. Avoid the disabled
    # "Make N required selection" placeholder and any checkout/pay buttons.
    if _click_add_cta(scope, page):
        return True

    # Last-resort fallback using simple role lookups
    for pattern in [r"^add to cart", r"^add \d+ to cart", r"^add item", r"^add for \$"]:
        try:
            btn = page.get_by_role("button", name=re.compile(pattern, re.I)).last
            try:
                label = btn.get_attribute("aria-label", timeout=500) or ""
            except Exception:
                label = ""
            if _CHECKOUT_TEXT.search(label):
                continue
            btn.click(timeout=2500)
            return True
        except Exception:
            continue
    return False


def _select_first_radio_per_group(scope, page):
    # 1) Native <input type="radio"> — pick first unchecked per `name` group
    try:
        radios = scope.locator("input[type='radio']").all()
    except Exception:
        radios = []

    seen_groups = set()
    for radio in radios:
        try:
            name = radio.get_attribute("name", timeout=500) or ""
            if name in seen_groups:
                continue
            # Skip group if any radio in it is already checked
            if name:
                try:
                    group_checked = scope.locator(
                        f"input[type='radio'][name='{name}']:checked"
                    ).count()
                    if group_checked > 0:
                        seen_groups.add(name)
                        continue
                except Exception:
                    pass
            # Prefer clicking the wrapping label for reliability
            label = radio.locator("xpath=ancestor::label[1]")
            clicked = False
            try:
                label.first.scroll_into_view_if_needed(timeout=1500)
                label.first.click(timeout=2000)
                clicked = True
            except Exception:
                pass
            if not clicked:
                try:
                    radio.scroll_into_view_if_needed(timeout=1500)
                    radio.click(timeout=2000, force=True)
                    clicked = True
                except Exception:
                    pass
            seen_groups.add(name)
        except Exception:
            continue

    # 2) ARIA radios (custom design-system controls without native input)
    try:
        aria_radios = scope.locator("[role='radio']").all()
    except Exception:
        aria_radios = []

    seen_aria = set()
    for radio in aria_radios:
        try:
            # Identify the group via aria-labelledby or parent id
            group_key = (
                radio.get_attribute("aria-labelledby", timeout=300)
                or radio.evaluate("el => el.parentElement?.id || ''")
                or ""
            )
            if group_key in seen_aria:
                continue
            checked = (radio.get_attribute("aria-checked", timeout=300) or "").lower()
            if checked == "true":
                seen_aria.add(group_key)
                continue
            radio.scroll_into_view_if_needed(timeout=1500)
            try:
                radio.click(timeout=2000)
            except Exception:
                radio.click(timeout=2000, force=True)
            seen_aria.add(group_key)
        except Exception:
            continue

    # 3) Last-ditch: if nothing was clicked above, look for a labeled
    # "Required" section and click the first option-like row inside it.
    try:
        if not seen_groups and not seen_aria:
            required_label = scope.get_by_text(
                re.compile(r"\bRequired\b", re.I)
            ).first
            try:
                required_label.scroll_into_view_if_needed(timeout=1500)
            except Exception:
                pass
            # Click the first sibling row that has a price tag like "+$X.XX"
            scope.evaluate(
                """() => {
                    const modal = document.querySelector('[role="dialog"], [aria-modal="true"]') || document.body;
                    const all = Array.from(modal.querySelectorAll('label, [role="option"], button, div'));
                    const target = all.find(el => {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (!t || t.length > 80) return false;
                        if (!/\\+\\$\\d/.test(t)) return false;
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 40 && rect.height > 20 &&
                            style.visibility !== 'hidden' && style.display !== 'none';
                    });
                    if (target) { target.scrollIntoView({block: 'center'}); target.click(); }
                }"""
            )
            try:
                page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass


def _click_add_cta(scope, page):
    # Try Playwright locator first — handles in-viewport scrolling cleanly.
    cta_patterns = [
        re.compile(r"^add\s+to\s+cart", re.I),
        re.compile(r"^add\s+\d+\s+to\s+cart", re.I),
        re.compile(r"^add\s+item", re.I),
        re.compile(r"^add\s+for\s+\$", re.I),
        re.compile(r"^add\s+.+\$", re.I),
    ]
    for pattern in cta_patterns:
        try:
            btn = scope.get_by_role("button", name=pattern).last
            text = (btn.inner_text(timeout=500) or "")
            if _CHECKOUT_TEXT.search(text):
                continue
            if re.search(r"make\s+\d+\s+required\s+selection|select\s+at\s+least", text, re.I):
                continue
            btn.scroll_into_view_if_needed(timeout=1500)
            btn.click(timeout=2500)
            return True
        except Exception:
            continue

    # JS fallback: pick the bottom-most enabled "Add" button in the modal
    try:
        clicked = page.evaluate(
            """() => {
                const modal = document.querySelector('[role="dialog"], [aria-modal="true"]') || document.body;
                const buttons = Array.from(modal.querySelectorAll('button, [role="button"]')).filter(b => {
                    const rect = b.getBoundingClientRect();
                    const style = getComputedStyle(b);
                    if (rect.width < 100 || rect.height < 30) return false;
                    if (style.visibility === 'hidden' || style.display === 'none') return false;
                    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
                    return true;
                });
                const bad = /checkout|sign\\s*in|log\\s*in|close|cancel|reviews?|subscribe|dashpass|place\\s+order|pay\\b|buy\\b/i;
                const stillRequired = /make\\s+\\d+\\s+required\\s+selection|select\\s+at\\s+least|select\\s+\\d+/i;
                const goodAdd = /\\badd\\b/i;
                const matches = buttons.filter(b => {
                    const t = ((b.innerText || b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().trim();
                    if (bad.test(t)) return false;
                    if (stillRequired.test(t)) return false;
                    return goodAdd.test(t);
                });
                if (matches.length === 0) return false;
                const target = matches[matches.length - 1];
                target.scrollIntoView({block: 'center'});
                target.click();
                return true;
            }"""
        )
        return bool(clicked)
    except Exception:
        return False


def _cart_count(page):
    try:
        label = page.get_by_label(re.compile(r"items?.*cart|open Order Cart", re.I)).first.get_attribute(
            "aria-label", timeout=1500
        )
    except Exception:
        label = ""
    match = re.search(r"(\d+)\s+items?", label or "")
    return int(match.group(1)) if match else 0


# ----------------------------------------------------------------------------
# Misc helpers
# ----------------------------------------------------------------------------

def _guarded_task(task, plan):
    return (
        "Operate the user's logged-in DoorDash session in visible Chrome. "
        "You may search restaurants/items, prepare a cart, remove items, or replace items. "
        "NEVER click checkout, place order, submit payment, subscribe, buy, or anything "
        "that would commit money. Stop one step BEFORE any irreversible action. "
        f"Action: {plan.get('action')}; search_term: {plan.get('search_term')}; "
        f"remove_query: {plan.get('remove_query')}. "
        f"Caller request: {task}"
    )


def _coerce_plan(plan):
    plan = dict(plan or {})
    action = str(plan.get("action") or "").strip().lower()
    if action not in SAFE_ACTIONS:
        action = "open"
    plan["action"] = action
    plan["search_term"] = str(plan.get("search_term") or "").strip()
    plan["remove_query"] = str(plan.get("remove_query") or "").strip()
    plan["browser_task"] = str(plan.get("browser_task") or "").strip()
    return plan


def _visible_blocker(page):
    try:
        content = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        return None
    if "access denied" in content:
        return "DoorDash blocked access in the browser. No cart changes were made."
    if "verify you are human" in content or "captcha" in content:
        return "DoorDash is asking for human verification. Complete it in Chrome, then send the request again."
    return None
