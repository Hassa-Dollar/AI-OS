# Runbook — running Shrink locally

Prereqs: Node 22, npm, the **Stripe CLI** (`stripe`), and a Stripe account in **TEST mode** (test keys only).

## 1. Environment
```
cp .env.example .env
# fill TEST values; generate the auth secret with:  openssl rand -hex 32
```

## 2. API (`components/api`) — available after T01+
```
cd components/api
npm ci
npm run dev          # http://localhost:8787
```

## 3. Web (`components/web`) — available after T09+
```
cd components/web
npm ci
npm run dev          # http://localhost:5173
```

## 4. Stripe webhooks (billing, T07+)
```
stripe login
stripe listen --forward-to localhost:8787/api/webhooks/stripe
# copy the printed whsec_… into STRIPE_WEBHOOK_SECRET in .env, then restart the API
# manual trigger:  stripe trigger checkout.session.completed
```

## 5. Test card (Stripe test mode)
`4242 4242 4242 4242` · any future expiry · any CVC · any postal code.

## 6. Tests
```
(cd components/api && npm run -s ci)   # lint + typecheck + test + coverage
(cd components/web && npm run -s ci)
# golden-path e2e (after T17): see e2e/ (Playwright) — runs api + web + SQLite together
```

## 7. Smoke the full flow (manual)
Sign up → create a link → open the short URL (click recorded) → upgrade with the test card →
webhook flips plan to `pro` → analytics unlocks. Free accounts cap at 10 links and get `402` on analytics.
