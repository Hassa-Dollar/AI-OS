# Task Completion Report — 000-example-health-endpoint

**Branch:** `task/000-example-health-endpoint`
**Model:** opencode-go/glm-5.1
**Status:** Done

## Acceptance Criteria

- [x] `GET /health` returns 200 and JSON body with `status: "ok"`
- [x] `uptime_s` is a non-negative integer (process uptime in seconds)
- [x] Tests cover: 200 path, body shape, uptime type
- [x] typecheck + lint pass; diff coverage ≥ 90%

## Files Changed

| File | Change |
|---|---|
| `src/routes/health.ts` | New — health route handler |
| `src/routes/health.test.ts` | New — 2 test cases |
| `src/routes/index.ts` | Modified — register health route |

## Coverage

- `health.ts`: 100% statements, branches, functions, lines
- Overall: 92.3% statements (uncovered lines 21-22 in `app.ts` are pre-existing catch block, not part of this diff)

## Gate Results

- `npm run typecheck`: pass
- `npm run lint`: pass
- `npm test`: 4/4 pass
- `npm run coverage`: pass

## Working Notes

- Used `Math.floor(process.uptime())` to get integer seconds as required by spec.
- No new dependencies added. Only `node:http` types used.
- Route registered as named export `health` from `./health`, imported in `index.ts`.