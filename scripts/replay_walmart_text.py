import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Replay a Walmart text request through the Concorde Flask app.")
    parser.add_argument("message", nargs="?", default="Change my Walmart cereal substitution")
    parser.add_argument("--session-id", default="local-walmart")
    parser.add_argument("--caller-phone", default="+13185160977")
    parser.add_argument("--live", action="store_true", help="Allow a live Browser Use run instead of dry-run mode.")
    args = parser.parse_args()

    if not args.live:
        os.environ.setdefault("BROWSER_USE_DRY_RUN", "1")
    os.environ.setdefault("WALMART_MODE", "browser")

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from app import app

    payload = {
        "session_id": args.session_id,
        "caller_phone": args.caller_phone,
        "message": args.message,
    }

    with app.test_client() as client:
        response = client.post("/api/walmart/text", json=payload)
        print(response.status_code)
        print(json.dumps(response.get_json(), indent=2))


if __name__ == "__main__":
    main()
