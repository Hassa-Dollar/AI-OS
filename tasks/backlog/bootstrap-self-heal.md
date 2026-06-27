# Backlog: bootstrap/doctor robustness — broken-setup matrix + deeper self-heal

> Status: backlog (capture only) — AFTER the SaaS. Raised by the operator once #82 shipped (doctor + bootstrap
> validated 10/10 on a healthy machine). Do NOT implement without a spec. Theme-adjacent to
> tasks/backlog/self-healing-ci.md.

## Idea
#82 gave us `bootstrap.sh` (provision) + `scripts/doctor.sh` (verify / auto-install / probe). It works on a
healthy machine. Harden it for UNHEALTHY ones — deliberately test first-launch on setups missing pieces, and
make the doctor self-heal more of them rather than only guiding.

- **Broken-setup test matrix:** missing sqlite3 / node / gh / opencode; opencode installed but not
  subscribed; subscribed but not connected; wrong Node version; no apt; no sudo; offline. Assert the doctor
  detects + (where safe) fixes, else guides correctly and exits non-zero. Ideally a clean container per case.
- **Deeper self-heal:** robust opencode install (npm prefix + PATH), gh via its apt repo, Node 22 via
  nvm/nodesource, gitleaks via release — each idempotent + verified, not merely "guided".
- **Probe hardening:** timeout the `opencode run` probe; distinguish not-installed vs not-subscribed vs
  not-connected vs gateway-down, each with a specific remedy.

## Why deferred
The SaaS (T01) is the real test and the priority; bootstrap works on the current machine. This is robustness
for future clones / fresh machines — best driven by real failures we hit, not speculation. Overlaps the
sandbox/self-heal work in self-healing-ci.md.
