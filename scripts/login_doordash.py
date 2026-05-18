"""One-time DoorDash login capture using the real Chrome over CDP.

Launches the user's actual Google Chrome binary with remote debugging enabled
against a dedicated Concorde profile directory. The user signs in interactively
(Google, email, SMS, Apple — all work because Cloudflare/Google see a normal
Chrome session). The profile dir persists the login for later automation runs.

Chrome is intentionally left running at the end so the automation can connect
straight away without restarting it.
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.doordash_browser import (  # noqa: E402
    CDP_PORT,
    _chrome_profile_dir,
    _cdp_url,
    _is_cdp_alive,
    _launch_real_chrome_with_cdp,
    _wait_for_cdp,
)


DOORDASH_LOGIN_URL = "https://www.doordash.com/consumer/login/"


def main():
    profile_dir = _chrome_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    if _is_cdp_alive():
        print(
            f"Chrome is already running with remote debugging on port {CDP_PORT}. Using it."
        )
    else:
        try:
            _launch_real_chrome_with_cdp(DOORDASH_LOGIN_URL)
        except FileNotFoundError as error:
            print(f"Could not launch Chrome: {error}", file=sys.stderr)
            print(
                "Set DOORDASH_CHROME_BINARY to the path of your Chrome binary.",
                file=sys.stderr,
            )
            return 1
        except Exception as error:
            print(f"Could not launch Chrome: {error}", file=sys.stderr)
            return 1
        if not _wait_for_cdp(timeout=15.0):
            print(
                f"Chrome did not expose remote debugging on port {CDP_PORT} in time.",
                file=sys.stderr,
            )
            print(
                "Quit any existing Chrome windows and try again, or set DOORDASH_CDP_PORT.",
                file=sys.stderr,
            )
            return 1

    print("")
    print("=" * 60)
    print("DoorDash login — using your real Chrome")
    print("=" * 60)
    print(f"Chrome opened with a dedicated Concorde profile at:")
    print(f"    {profile_dir}")
    print("")
    print("Sign in to DoorDash using ANY method (Google, email, SMS, Apple).")
    print("This is your real Chrome, so it should work normally.")
    print("")
    print("When you're signed in and see the home page, come back here")
    print("and press Enter.")
    print("=" * 60)
    print("")
    input("Press Enter once you're logged in...")

    # Soft sanity check via Playwright CDP connect.
    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        print(f"Note: skipping sanity check (playwright unavailable: {error}).")
    else:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(_cdp_url())
                try:
                    context = browser.contexts[0] if browser.contexts else None
                    page = None
                    if context is not None:
                        page = next(
                            (pg for pg in context.pages if "doordash.com" in (pg.url or "")),
                            None,
                        )
                    if page is None:
                        print(
                            "Warning: I could not find a DoorDash tab in your Chrome — "
                            "re-run if needed."
                        )
                    else:
                        body_text = ""
                        try:
                            body_text = page.locator("body").inner_text(timeout=3000).lower()
                        except Exception:
                            pass
                        sign_in_visible = (
                            "sign in" in body_text and "account" not in body_text
                        )
                        if sign_in_visible:
                            print(
                                "Looks like you may not be signed in yet — re-run if needed."
                            )
                finally:
                    # Detach the Playwright client without killing Chrome.
                    try:
                        browser.close()
                    except Exception:
                        pass
        except Exception as error:
            print(f"Note: sanity check skipped ({error}).")

    print("")
    print(
        "Done. Login saved in profile. Chrome will stay open in the background for "
        "the automation to use. To close it later, just quit Chrome."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
