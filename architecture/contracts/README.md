# Contracts

Machine-checkable interfaces between modules: OpenAPI specs, JSON Schema, protobuf, or typed
stubs. A contract is the boundary a worker implements *against* but may never change on its own.

## Rules
- Designing or changing a contract is HIGH leverage → the **Lead** owns it; record the change
  in an ADR (`architecture/adr/`). A worker who needs a contract change must STOP and escalate
  (AGENTS.md §3).
- A task spec lists the contracts it touches under `depends_on_contracts:`. The risk router
  (`scripts/gate.sh`) flags any diff that edits files here and routes it to the Opus gate.
- One file per contract; name it for the boundary, e.g. `payments-api.yaml`, `user.schema.json`.
