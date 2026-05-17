import { createHmac, timingSafeEqual } from "node:crypto";

export function signAgentPhoneWebhook(rawBody, timestamp, secret) {
  const signedPayload = `${timestamp}.${rawBody}`;
  const digest = createHmac("sha256", secret).update(signedPayload).digest("hex");
  return `sha256=${digest}`;
}

export function verifyAgentPhoneWebhook(rawBody, signature, timestamp, secret, nowSeconds = Date.now() / 1000) {
  if (!secret) return { ok: true, skipped: true };
  if (!signature || !timestamp) return { ok: false, reason: "missing signature headers" };

  const timestampSeconds = Number(timestamp);
  if (!Number.isFinite(timestampSeconds)) return { ok: false, reason: "invalid timestamp" };

  const age = Math.abs(nowSeconds - timestampSeconds);
  if (age > 300) return { ok: false, reason: "timestamp outside 5 minute replay window" };

  const expected = signAgentPhoneWebhook(rawBody, timestamp, secret);
  const expectedBytes = Buffer.from(expected);
  const actualBytes = Buffer.from(signature);

  if (expectedBytes.length !== actualBytes.length) {
    return { ok: false, reason: "signature mismatch" };
  }

  return {
    ok: timingSafeEqual(expectedBytes, actualBytes),
    reason: "signature mismatch"
  };
}
