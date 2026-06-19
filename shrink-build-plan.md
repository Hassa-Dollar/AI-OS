# Sprint Plan — "Shrink" SaaS (the full hard run)

> Purpose: exercise **all seven catalog models** end-to-end by having the workforce build, test, and run a
> complete SaaS locally — full UI, authentication, database, and real payments. This is the Lead's keystone
> plan (CLAUDE.md §2). Decisions locked with the operator: **real Stripe (test mode)**, **Better Auth + Hono**
> (library, self-hosted, no account), **hybrid tests** (unit + integration everywhere + one Playwright golden-path
> e2e), **full plan up front**.

---

## 1. What this proves

A pass means the loop carried a real product: every model did its bound job, P8 held on every diff, the
risk router escalated auth/payments to the human gate, the catalog guard held, and both components built,
tested, and ran locally. Model coverage:

| Model | Family | Role in this run | Tasks |
|---|---|---|---|
| GLM-5.2 | zhipu | primary implementer (API + some web) | T01, T04, T06, T11, T16 |
| Qwen3.7-Plus | alibaba | parallel implementer | T05, T13, T15 (+verify mimo) |
| Kimi K2.7-Code | moonshot | autonomous (multi-file: auth, payments, e2e) | T02, T03, T07, T08, T10, T17 |
| DeepSeek V4 Pro | deepseek | primary verifier | QA on most diffs |
| Qwen3.7-Max | alibaba | researcher (decision memos) | T00-R |
| MiMo-V2.5-Pro | xiaomi | scribe (docs, completion reports) | T18 |
| MiniMax M3 | minimax | **frontend implementer (finally bound)** | T09, T12, T14 (+T10 with Kimi) |

P8 pairings used (verifier family ≠ author family): zhipu↔deepseek, alibaba↔{deepseek,moonshot},
moonshot↔deepseek, minimax↔{deepseek,moonshot}, xiaomi↔alibaba. All valid.

---

## 2. Product spec — "Shrink"

A URL shortener SaaS.

- **Free tier:** up to 10 links; redirects; no analytics.
- **Pro tier (Stripe subscription):** unlimited links + click analytics (per-link totals + a time series).
- **Auth:** email + password, server sessions (Better Auth).
- **Core flows:** sign up / log in → create short link → public redirect records a click → upgrade to Pro
  (Stripe Checkout) → analytics unlocked → manage subscription (Stripe portal).

Testable locally end-to-end: create a link, `curl` the short URL, watch the click count rise, confirm
analytics is 402-gated on free and visible on Pro after a test-card upgrade.

---

## 3. Architecture

Two extractable components (ADR-0002), contract-first (they never import each other's source — they agree
on a contract and talk over HTTP).

```
components/api/   profile web-app/ts-hono-api   Hono + @hono/node-server + Better Auth + better-sqlite3 + stripe + zod
components/web/   profile web-app/react-vite    React + Vite + TS + react-router + Tailwind
architecture/contracts/shrink-api.md            the HTTP contract both sides implement to
architecture/contracts/shrink-db-schema.md      the SQLite schema + plan limits
e2e/                                            Playwright golden-path (drives both running servers; not a component)
```

**Why Hono (a deviation from the `ts-node-service` "no-framework" rule):** Better Auth — the current
bulletproof, self-hosted, no-account TS auth library (Lucia is deprecated as of 2025) — wants a
web-standard `Request`/`Response` handler, which Hono provides cleanly via `@hono/node-server`. Routing,
middleware, and the Stripe webhook raw-body handling are also far cleaner than hand-rolled `node:http`.
This is recorded in **ADR-0012** and isolated in a **new profile** so the minimal `ts-node-service` profile
is untouched.

**Secrets:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `BETTER_AUTH_SECRET` live in a gitignored
`.env` (read from `process.env`); a committed `.env.example` documents them. gitleaks (os-ci) blocks leaks.

**Local Stripe webhooks:** the operator runs `stripe listen --forward-to localhost:8787/api/webhooks/stripe`
(Stripe CLI) during payment testing.

---

## 4. Phase 0 — Lead setup (authored by Opus, not dispatched to workers)

These create the scaffolding everything else depends on. They land via `pr.sh` (chore branches).

| # | Deliverable | File(s) |
|---|---|---|
| P0.1 | **ADR-0011** — Shrink architecture (2 components, contract-first, stack, gate map) | `architecture/adr/0011-*.md` |
| P0.2 | **ADR-0012** — adopt Hono + Better Auth for the API profile | `architecture/adr/0012-*.md` |
| P0.3 | **ADR-0013** — multi-component product-ci (matrix over `components/*`) | `architecture/adr/0013-*.md` |
| P0.4 | **API contract** — every endpoint, shapes, status codes, authz, plan-gating | `architecture/contracts/shrink-api.md` |
| P0.5 | **DB schema contract** — tables, indexes, plan limits | `architecture/contracts/shrink-db-schema.md` |
| P0.6 | **Backend profile** `web-app/ts-hono-api` (profile.json, conventions.md, ci-env.sh, product-ci? see P0.8, product-skeleton) | `profiles/web-app/ts-hono-api/**` |
| P0.7 | **Frontend profile** `web-app/react-vite` (binds MiniMax M3) | `profiles/web-app/react-vite/**` |
| P0.8 | **Multi-component CI** — `product-ci.yml` runs a matrix over `components/*` (each runs `npm ci && npm run -s ci`); update branch protection to require it | `.github/workflows/product-ci.yml` |
| P0.9 | `.env.example` + secrets/runbook note in `docs/` | `.env.example`, `docs/runbooks/shrink-local.md` |

Profile role bindings (all on-catalog, ADR-0009):

| Role | Backend (`ts-hono-api`) | Frontend (`react-vite`) |
|---|---|---|
| implementer | glm-5.2 | minimax-m3 |
| implementer_secondary | qwen3.7-plus | glm-5.2 |
| autonomous | kimi-k2.7-code | kimi-k2.7-code |
| verifier | deepseek-v4-pro | deepseek-v4-pro |
| researcher | qwen3.7-max | qwen3.7-max |
| scribe | mimo-v2.5-pro | mimo-v2.5-pro |
| unbound | minimax-m3 | qwen3.7-plus |

After P0: `scripts/profile.sh apply web-app/ts-hono-api api` and `… react-vite web` scaffold the two
components; then the worker tasks below run.

---

## 5. The task breakdown (T01–T19)

Gate legend: **AUTO** = expected to auto-merge (CI + clean cross-family QA, no risk flags); **FLAG** =
risk-router escalates to the Opus gate (new-dep / large / contract); **HUMAN** = HUMAN-REQUIRED hard stop
(auth / payments / secrets) — never auto-merges (reviews/checklist.md).

| ID | Comp | Title | Model | Verifier | Auton. | Blast | Gate | Deps (pre-approved) | depends_on |
|---|---|---|---|---|---|---|---|---|---|
| T00-R | — | Research memo: Better Auth + Hono + Stripe (test mode) + better-sqlite3 wiring | qwen3.7-max | deepseek | – | low | FLAG | – | P0 |
| T01 | api | Scaffold Hono server + tooling (tsconfig strict, vitest, eslint, `ci` script) + /healthz | glm-5.2 | deepseek | – | low | FLAG(dep) | hono, @hono/node-server | P0 |
| T02 | api | SQLite layer: connection + migration runner + app tables | kimi-k2.7-code | deepseek | yes | med | FLAG(dep) | better-sqlite3 | T01 |
| T03 | api | Better Auth (email/password + sessions) on Hono + `/api/me` | kimi-k2.7-code | deepseek | yes | high | **HUMAN** | better-auth | T02 |
| T04 | api | Links: create/list/delete + free-plan limit (10) + zod validation | glm-5.2 | deepseek | – | med | FLAG(dep) | zod | T03 |
| T05 | api | Public redirect `GET /:code` (302) + click recording | qwen3.7-plus | kimi | – | med | AUTO | – | T02 |
| T06 | api | Analytics endpoint (Pro-gated; 402 on free) | glm-5.2 | deepseek | – | med | AUTO | – | T04, T05 |
| T07 | api | Stripe Checkout + customer portal endpoints | kimi-k2.7-code | deepseek | yes | high | **HUMAN** | stripe | T03 |
| T08 | api | Stripe webhook (raw-body signature verify → subscription state) | kimi-k2.7-code | deepseek | yes | high | **HUMAN** | – | T07 |
| T09 | web | Scaffold Vite+React+TS + router + Tailwind + test setup + `ci` script | minimax-m3 | deepseek | – | low | FLAG(dep) | react, react-dom, vite, @vitejs/plugin-react, react-router-dom, tailwindcss, @testing-library/react, jsdom | P0 |
| T10 | web | Auth UI (signup/login) + Better Auth client + session wiring | kimi-k2.7-code | deepseek | yes | high | **HUMAN** | @better-auth/client (if separate) | T09, T03 |
| T11 | web | App shell + nav + auth guard + `/api/me` plan badge | glm-5.2 | deepseek | – | med | AUTO | – | T10 |
| T12 | web | Dashboard: create-link form + list (copy/delete) | minimax-m3 | deepseek | – | med | AUTO | – | T11, T04 |
| T13 | web | Analytics page (Pro-gated UI) | qwen3.7-plus | kimi | – | med | AUTO | – | T12, T06 |
| T14 | web | Billing/upgrade page (Checkout + manage subscription) | minimax-m3 | deepseek | – | high | **HUMAN** | – | T11, T07 |
| T15 | api | API integration tests (auth+links+redirect+analytics+webhook, Stripe stubbed) | qwen3.7-plus | deepseek | – | med | AUTO | – | T03–T08 |
| T16 | web | Web component tests (dashboard, billing gating, analytics gating) | glm-5.2 | kimi | – | med | AUTO | – | T12–T14 |
| T17 | e2e | Playwright golden-path: signup→create→redirect→upgrade(test card)→analytics | kimi-k2.7-code | deepseek | yes | high | **HUMAN** | @playwright/test | T15, T16 |
| T18 | docs | README + `docs/runbooks/shrink-local.md` (run api+web+stripe CLI) | mimo-v2.5-pro | qwen3.7-plus | – | low | AUTO | – | T17 |

19 worker tasks (T00-R … T18). Roughly **6 HUMAN-gated** (auth/payments surfaces) — expected and the point.

---

## 6. Per-task detail (Goal + Acceptance criteria)

> Each becomes a full spec via `scripts/new-task.sh <id> <slug> <model> <verifier>`, then edited to add
> `files_allowed` (disjoint, one component), `deps_preapproved`, and these criteria. Out-of-scope + stop
> conditions per the schema (manual §6.6).

**T00-R — research memo.** Goal: a decision memo in `knowledge/external/` covering Better Auth setup on
Hono (email/password + sessions, SQLite adapter), Stripe test-mode Checkout+webhook flow, and better-sqlite3
migration pattern. AC: concrete API surface + gotchas for T03/T07/T08; recommended package versions; no code.

**T01 — api scaffold.** AC: `components/api` builds (`tsc --noEmit`), `npm run -s ci` runs lint+typecheck+test,
Hono server boots via `@hono/node-server`, `GET /healthz` → 200 `{status:"ok"}`, one passing test, diff
coverage ≥90% on new logic.

**T02 — SQLite layer.** AC: a single DB module opens `better-sqlite3`; an idempotent migration runner applies
versioned SQL; tables `link`, `click`, `subscription` created per `shrink-db-schema.md`; unit tests on the
migrator (fresh DB → all tables; re-run → no-op); WAL mode on.

**T03 — Better Auth (HUMAN).** AC: email/password signup + login + logout via Better Auth mounted on Hono;
sessions persisted in SQLite; `GET /api/me` returns the user + plan (`free` default) or 401; passwords never
logged; secret read from `BETTER_AUTH_SECRET`. Security review required (auth hard stop).

**T04 — links CRUD.** AC: `POST /api/links` validates URL (zod), generates a unique code, rejects when a free
user already has 10 (402/403 with a clear body); `GET /api/links` lists only the caller's links; `DELETE
/api/links/:code` only by owner; integration tests cover limit + ownership.

**T05 — redirect + click.** AC: `GET /:code` → 302 to target (404 if unknown); inserts a `click` row
(ts, referrer, UA, salted IP hash — no raw IP); redirect path adds no auth; test asserts a click is recorded.

**T06 — analytics.** AC: `GET /api/links/:code/analytics` returns totals + a daily time series for the owner;
**402 for free-plan** users; tests cover the Pro/free branch and owner check.

**T07 — Stripe Checkout/portal (HUMAN).** AC: `POST /api/billing/checkout` returns a Checkout Session URL for
the Pro price; `POST /api/billing/portal` returns a portal URL; keys from env; no secret in logs/responses;
amounts/price id from config. Payments + secrets hard stop.

**T08 — Stripe webhook (HUMAN).** AC: `POST /api/webhooks/stripe` verifies the signature against
`STRIPE_WEBHOOK_SECRET` over the **raw** body; `checkout.session.completed` / `customer.subscription.*`
update the `subscription` row (plan, status, period end); invalid signature → 400; idempotent on retries.

**T09 — web scaffold.** AC: Vite+React+TS app builds; router in place; Tailwind configured; `npm run -s ci`
runs lint+typecheck+test; Testing Library + jsdom set up; a smoke test renders the app shell.

**T10 — auth UI (HUMAN).** AC: signup + login + logout pages call Better Auth; session reflected in UI;
errors surfaced; protected routes redirect to login; no credential logging. Auth-surface review.

**T11 — app shell.** AC: nav, auth guard, and a plan badge driven by `/api/me`; unauthenticated users routed
to login; component test for the guard.

**T12 — dashboard.** AC: create-link form (optimistic add), list with copy-to-clipboard + delete, free-limit
message when blocked; component tests with fetch mocked.

**T13 — analytics page.** AC: per-link analytics view; **Pro-gated UI** (upsell when free / 402); renders the
time series; tests cover gated vs unlocked.

**T14 — billing page (HUMAN).** AC: "Upgrade" → Checkout redirect; "Manage subscription" → portal; reflects
current plan from `/api/me`; payment-surface review.

**T15 — API integration tests.** AC: in-process Hono app against a temp SQLite DB; covers auth, link limit,
redirect+click, analytics gating, and webhook state transition (Stripe network stubbed); coverage ≥90% diff.

**T16 — web component tests.** AC: dashboard, billing, analytics gating covered with mocked API; no real network.

**T17 — Playwright e2e (HUMAN).** AC: one scripted browser run: signup → create link → hit redirect → upgrade
with Stripe test card `4242 4242 4242 4242` → webhook flips plan → analytics visible. Runs against api+web+
SQLite locally; documented in the runbook. Payment flow → human review.

**T18 — docs.** AC: `README` quickstart + `docs/runbooks/shrink-local.md`: env setup, `stripe listen`, run both
dev servers, run tests + e2e. Scribe writes from the merged state only.

---

## 7. Ordering, parallelism, and the run procedure

**Critical path:** P0 → T01 → T02 → T03 → (T04, T05) → T06 → T07 → T08 → web (T09 → T10 → T11 → T12/T13/T14)
→ T15/T16 → T17 → T18.

**Safe parallelism** (disjoint `files_allowed`, enforced by dispatch.sh): T05 ∥ T04 (different route files),
T13 ∥ T16 prep, T15 (api) ∥ web tasks. Never two active tasks sharing a file.

**Per task the operator runs:**
```
scripts/new-task.sh <id> <slug> <model> <verifier>     # then edit files_allowed + deps_preapproved + AC
scripts/dispatch.sh <id>                               # branch + worker (opencode)
scripts/ship.sh <id>                                   # gate (CI + cross-family QA + risk router) → land/queue
```
For **HUMAN** tasks, `ship.sh` will route to the Opus gate / draft PR instead of auto-merging; the operator
+ Lead review (prompts/code-review.md Opus addendum) before merge.

---

## 8. Risks / gaps (carried from the planning discussion)

1. **Multi-component CI** is the one true loop gap — fixed in P0.8 before web work (matrix over `components/*`).
2. **Contract drift** between api/web — the `shrink-api.md` contract is the single source of truth; any change
   is a Lead diff (FLAG/HUMAN), never a worker's.
3. **Secrets** — `.env` gitignored; `.env.example` committed; gitleaks enforces; Stripe **test** keys only.
4. **Webhook localhost** — needs `stripe listen` (operator-side, documented in T18 runbook).
5. **Opus budget** — ~6 HUMAN gates + several FLAGs; pace per CLAUDE.md §7 (target <8 Opus msgs/merged task).
   If first-pass QA dips <60–70%, stop and tighten specs before dispatching more.
6. **Model availability** — all seven validated this session; the catalog guard (ADR-0009) blocks drift.

---

## 9. Definition of done

`main` builds; `os-ci` + the multi-component `product-ci` green; both components run locally; the Playwright
golden path passes; a free user is capped at 10 links and 402-gated on analytics; a Pro user (after a Stripe
test-card upgrade) has unlimited links + analytics; all 19 tasks merged and stayed merged; the run exercised
every one of the seven models in its role.
