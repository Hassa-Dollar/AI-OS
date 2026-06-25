# product-skeleton — web-app/ts-node-service

Starting files for a **new** component of this profile.

**Deliberately minimal (ADR-0003 build scope: build a component only when needed).** This profile has no
reference implementation in the repo today. To scaffold a `web-app/ts-node-service` component:

1. `scripts/profile.sh apply web-app/ts-node-service <new-name>` (copies this skeleton + records the binding).
2. Add the Node/TS `node:http` stack files: `package.json` (with the `ci` script), `tsconfig` (strict),
   ESLint, Vitest, and a minimal `src/` (`server.ts`, `app.ts`, one route + test).

A fuller canonical skeleton can be filled in when this profile is first actually used — not built speculatively.
