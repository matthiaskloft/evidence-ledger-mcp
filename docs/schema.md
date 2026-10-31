# Schema versions and storage

The schema and server have independent versions, repositories and releases. This server vendors an exact schema revision in [`schema/`](../schema/); [schema/UPSTREAM.json](../schema/UPSTREAM.json) records the upstream commit and file hashes. Builds and runtime validation do not fetch the schema. Original `schema-v*` releases here remain historical records; future schema releases belong in the schema repository.

To adopt a new schema release, follow [schema/README.md](../schema/README.md).

## Storage format

The server stores ledgers as JSON Lines (`.jsonl`, one record per line), because new records are appended as single lines, concurrent additions rarely conflict, and agents write JSON reliably. It reads JSON Lines and exports JSON or JSON Lines; YAML ledgers written by hand remain valid under the schema.
