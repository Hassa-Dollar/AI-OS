# service — component

A TypeScript / `node:http` service (no framework). Governed by the `web-app/ts-node-service` profile
(`.component.yml`).

**Self-contained & extractable (ADR-0002).** Everything this component needs lives in this directory; it
references no path outside `components/service/`. Build and test it standalone:

```bash
cd components/service
npm ci
npm test
npm run dev      # local run
```

To lift it out of the OS, copy this directory anywhere — it carries its own `package.json`, lockfile,
config, and tests. The dependency is one-way: the OS reaches in (CI and `gate.sh` run `cd
components/service`); nothing here reaches back out. Cross-component calls, if ever needed, go through a
contract in `architecture/contracts/`.
