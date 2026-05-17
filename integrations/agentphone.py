import hmac
import hashlib
import time


def verify_webhook(raw_body, signature, timestamp, secret, now=None):
    if not secret:
        return {"ok": True, "reason": "verification_disabled"}
    if not signature or not timestamp:
        return {"ok": False, "reason": "missing_signature"}

    now = now or time.time()
    try:
        ts = int(timestamp)
    except ValueError:
        return {"ok": False, "reason": "invalid_timestamp"}
    if abs(now - ts) > 300:
        return {"ok": False, "reason": "stale_timestamp"}

    signed = f"{timestamp}.{raw_body}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    expected_header = f"sha256={expected}"
    if not hmac.compare_digest(signature, expected_header):
        return {"ok": False, "reason": "invalid_signature"}
    return {"ok": True, "reason": "verified"}
