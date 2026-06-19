# Contract: shrink-api (HTTP)

> **Lead-owned source of truth** for the Shrink HTTP API. `components/api` implements it; `components/web`
> consumes it. Neither imports the other's source (isolation, ADR-0002) — this document is the only
> coupling. Any change here is a risk-routed Lead diff (gate.sh flags `architecture/contracts/`), never a
> worker's. Governs ADR-0011.

## Conventions
- Base URL (local): `http://localhost:8787`. Web dev origin: `http://localhost:5173`.
- All bodies are JSON (`content-type: application/json`) unless noted (the Stripe webhook is raw).
- **Auth** is a session cookie issued by Better Auth. CORS allows the web origin with credentials.
- **Error model:** non-2xx returns `{ "error": { "code": "<CODE>", "message": "<human text>" } }`.
  Codes: `INVALID_INPUT`, `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `PLAN_LIMIT`, `PRO_REQUIRED`,
  `RATE_LIMITED`, `INTERNAL`.
- **Plans:** `free` (≤10 links, no analytics) and `pro` (unlimited links + analytics). Plan is derived from
  the `subscription` row (see shrink-db-schema.md).

## Auth (Better Auth, mounted)
Better Auth owns `/api/auth/*` (email+password signup, login, logout, session). The web app uses the
Better Auth client against these. Treat the exact sub-paths as Better Auth's documented surface; do not
re-implement them. Our only auth wrapper:

| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/api/me` | session | `200 { user: { id, email }, plan: "free"\|"pro" }` | `401 UNAUTHENTICATED` |

## Links
| Method | Path | Auth | Request | Success | Errors |
|---|---|---|---|---|---|
| POST | `/api/links` | session | `{ target_url: string (http/https) }` | `201 { code, short_url, target_url, created_at }` | `400 INVALID_INPUT`, `401`, `402 PLAN_LIMIT` (free at 10) |
| GET | `/api/links` | session | – | `200 [ { code, short_url, target_url, created_at, click_count } ]` | `401` |
| DELETE | `/api/links/:code` | session (owner) | – | `204` | `401`, `403 FORBIDDEN`, `404 NOT_FOUND` |
| GET | `/api/links/:code/analytics` | session (owner) | – | `200 { code, total_clicks, series: [ { date: "YYYY-MM-DD", count } ] }` | `401`, `402 PRO_REQUIRED` (free), `403`, `404` |

- `code`: short, URL-safe, unique (e.g. 7 chars base62). `short_url` = `${BASE_URL}/${code}`.
- `target_url` validated (must be http/https) — `zod`.

## Redirect (public)
| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/:code` | none | `302` `Location: <target_url>`; records a `click` (ts, referrer, UA, salted IP hash). `404 NOT_FOUND` if unknown. No body on success. |

Reserved top-level paths (never a code): `api`, `healthz`, `assets`, `favicon.ico`.

## Billing (Stripe, test mode)
| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| POST | `/api/billing/checkout` | session | `200 { url }` (Stripe Checkout Session for the Pro price) | `401` |
| POST | `/api/billing/portal` | session | `200 { url }` (Stripe Billing Portal) | `401`, `404 NOT_FOUND` (no customer yet) |
| POST | `/api/webhooks/stripe` | Stripe sig | `200 {}` | `400` (bad/absent `Stripe-Signature`) |

- Webhook body is the **raw** bytes; verify against `STRIPE_WEBHOOK_SECRET`. Handle
  `checkout.session.completed` and `customer.subscription.{created,updated,deleted}` → upsert the
  `subscription` row (plan/status/period end). Idempotent on retries.

## Health
| Method | Path | Response |
|---|---|---|
| GET | `/healthz` | `200 { status: "ok" }` |

## Notes for implementers
- Authn/authz: every `/api/links*` and `/api/billing*` route requires a session; ownership checked on
  per-link routes. The public redirect is the only unauthenticated app route.
- Plan gating is server-enforced (free→`402 PRO_REQUIRED` on analytics; free→`402 PLAN_LIMIT` at 10 links).
  The web app mirrors gating in UI but must not be the enforcement point.
