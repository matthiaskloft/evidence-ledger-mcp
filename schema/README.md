# Pinned upstream schema

The canonical schema is maintained in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema), independently of this server.

This directory vendors schema v0.5.1 from tag `schema-v0.5.1`. [UPSTREAM.json](UPSTREAM.json) records its exact upstream commit and SHA-256 hashes for the schema, licence and changelog. Do not edit those vendored files here. The wheel bundles the JSON schema and its CC BY 4.0 licence notice; validation and builds work offline.

To adopt a new schema release, retrieve these three files from that release's immutable commit, update the version, tag, revision and hashes in `UPSTREAM.json`, and update the README's supported schema version. Run the full server checks and build/distribution checks before merging. The tests verify the vendored files against the recorded hashes.

The schema identifier is preserved exactly as published upstream, using the upstream versioned raw GitHub namespace.
