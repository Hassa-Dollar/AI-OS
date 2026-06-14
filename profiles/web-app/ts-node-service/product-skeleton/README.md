# product-skeleton — web-app/ts-node-service

Starting files for a **new** component of this profile.

**v1 (deliberately minimal — ADR-0003 build scope: "build one component now").** The reference
implementation is `components/service/`. To add a second web-app/ts-node-service component today:

1. Copy from the reference: `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.js`,
   `vitest.config.ts`, and a minimal `src/` (`server.ts`, `app.ts`, one route + test).
2. `scripts/profile.sh apply web-app/ts-node-service <new-name>`.

A trimmed canonical skeleton will be extracted into this folder as part of the "add a second component"
increment — not built speculatively while only one component exists.
