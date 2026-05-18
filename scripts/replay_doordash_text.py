import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Replay a DoorDash text request through the Concorde Flask app.")
    parser.add_argument("message", nargs="?", default="Open DoorDash and add pizza to cart, but do not buy anything")
    parser.add_argument("--session-id", default="doordash-local")
    parser.add_argument("--caller-phone", default="+13185160977")
    parser.add_argument("--dry-run", action="store_true", help="Build the task without opening Chrome.")
    args = parser.parse_args()

    if args.dry_run:
        os.environ.setdefault("DOORDASH_DRY_RUN", "1")
    os.environ.setdefault("DOORDASH_BROWSER_PROFILE_ID", "Default")
    os.environ.setdefault("DOORDASH_KEEP_BROWSER_OPEN", "1")

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from app import app

    payload = {
        "session_id": args.session_id,
        "caller_phone": args.caller_phone,
        "message": args.message,
    }

    with app.test_client() as client:
        response = client.post("/api/doordash/text", json=payload)
        print(response.status_code)
        print(json.dumps(response.get_json(), indent=2))


if __name__ == "__main__":
    main()
