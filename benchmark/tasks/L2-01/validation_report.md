# L2-01 Validation Report

Validated 2026-08-28. Both fresh resets failed the same four route/detail checks. The oracle passed all six hidden checks. Pinned baseline and oracle Docker images were built; the baseline detail page returned HTTP 422, the oracle returned HTTP 200 with the expected item, and the JSON endpoint remained healthy. Fixture SHA-256: `bec7e413e7a74675fccc060bf3947dbf234dac74c70966a232f2f6fc5a28654f`.

Result: **PASS**.
