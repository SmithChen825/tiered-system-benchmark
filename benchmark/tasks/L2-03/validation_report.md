# L2-03 Validation Report

Validated 2026-08-29. The first reset failed exactly the four declared path and persistence checks: the seed notes did not load from the authoritative project store, import did not update that store, a restart from a different working directory did not reload the import, and the default path was not anchored to the project root. The researcher-authored one-line storage-path oracle passed all seven hidden checks. An independent second reset reproduced the same four failures.

Separate baseline and oracle Docker images were tested with isolated named volumes. The baseline started with no notes, accepted and exported an import only from its container layer, and returned to no notes after container recreation. The oracle loaded both seed notes from the mounted store, imported and exported the replacement backup, rejected a schema-invalid backup without data loss, and reloaded the imported notes after container recreation with the same named volume. Fixture SHA-256: `5e98cd59212a3dae996df3112b9c0d4ad9aad38d3d0aaae86e31f7d5020faf78`.

Result: **PASS**.

