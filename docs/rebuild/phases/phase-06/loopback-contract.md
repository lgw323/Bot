# PHASE 6 Discord ↔ Watch loopback contract

Date: 2026-09-10. Implemented in `watch/adapters/control_client.py`, `control_server.py`,
`control_schema.py` and `security.py`; no production listener is active.

## Transport and authentication

The Discord client accepts only an HTTP URL with literal loopback IP, explicit port, no credentials,
path, query or fragment. DNS, redirects and environment proxies are disabled. The internal ASGI app
is separate from the public ASGI app. Its socket peer must be a literal loopback address; forwarded
headers cannot grant trust. The inactive server factory binds both listeners to loopback on distinct
ports. The future public proxy must route only to the public listener.

POST `/internal/watch/{operation}` has an 8192-byte body cap, 8 admitted requests/client calls,
5-second client total deadline and 5-second internal dispatch deadline. Response cap is 64 KiB.
No automatic normal-call retry. Each attempt uses a fresh 128-bit random nonce and timestamp.

Headers: `X-Watch-Time` (UTC Unix seconds), `X-Watch-Nonce` (32 lowercase hex),
`X-Watch-Signature` (64 lowercase hex). Signature is HMAC-SHA256 over the exact bytes:

```text
POST\nPATH\nTIME\nNONCE\nBODY
```

The synthetic/operational key must contain at least 32 characters and should be an independently
generated random secret. ±30-second clock window; authenticated nonces retained for 61 seconds,
maximum 256, duplicate rejected. Bad signature/peer/time/nonce fail closed. Keys and raw bodies
never enter telemetry. Public requests cannot reach these operations.

## Envelope and schema

Request: `{"correlation":"32 lowercase hex","data":{...}}`.
Response: `{"correlation":"same value","data":{...}}`.
The signed body includes correlation; the server installs it in the Phase 2 context. It is opaque,
not derived from user IDs, URLs or capabilities. Client verifies echoed correlation and exact
operation-specific response shape. Duplicate JSON keys, unknown fields, non-finite numbers,
wrong types and malformed IDs are rejected.

| Operation | Exact request data | Success data / semantics |
| --- | --- | --- |
| create | guild, user: positive 63-bit integers; operation: 1–80 letters/digits/underscore/hyphen; issued: Unix integer | session_id: 64-hex digest; capability: 43 base64url; expires: finite Unix time; published: bool |
| bind | session_id; channel, message: positive 63-bit integers; admin: bool | `{}`; bind once or accept identical repeat; reject conflicting message identity |
| close | session_id | `{}`; terminal, idempotent; persist Discord cleanup receipt |
| abort | same four fields as create | `{}`; revoke even when create response was lost; tombstone blocks later create |
| status | `{}` | ready: bool; no session payload or secret |
| cleanup | `{}` | items: at most 100 rows, each session_id, channel, message, admin_channel, admin_message; nullable paired IDs |
| ack | session_id | `{}`; idempotently acknowledge known-message deletion |

Create retry identity is `(guild,user,operation,issued)`. Keep all four fields unchanged; issue time
must remain within the ±60-second admission window. An already closed operation cannot recreate
the session. Abort accepts an older issued time for cancellation but not a future time beyond that
window. Published intent status lets a repeated request avoid another public invite. Discord's
bounded 120-second interaction receipt also collapses simultaneous duplicate Gateway deliveries.

There is one configured Discord Gateway owner. This is not a multi-replica exactly-once Discord
delivery protocol. No Python object, actor reference, socket or mutable dictionary crosses the
boundary; tests serialize through the actual signed HTTP client/server using an in-process transport.

## Errors and recovery

Errors contain a safe `detail` and typed `code`, never raw exception/traceback/body. HTTP 400 is
validation, 403 authentication/authorization, 404 inactive session, 429 rate/capacity, 503 unavailable/
deadline/data failure. The client maps known typed codes and treats malformed/unexpected responses
as external failures. Unknown public paths remain 404; the framework may return standard 405/422
for route/method validation. ASGI ingress returns fixed 408/413 messages for body deadline/size.

An uncertain create is followed by abort using its original identity. Compensation has at most three
attempts within 2 seconds; exhaustion is recorded without a capability and never reported as normal
success. Known-message deletion is retried by bounded durable cleanup polling. Undeliverable messages
with unknown IDs and real process/proxy/network failures remain the explicit limitations in the
[Watch contract](watch-contract.md). No Redis, broker or external authentication service is used.
