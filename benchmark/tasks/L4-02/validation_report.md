# L4-02 Validation Report

Validated 2026-08-28. Both fresh resets failed the same four ORM/schema/create-mapping checks. The oracle passed all seven hidden checks. Baseline Compose started with columns `id,name,email,status` and two seeds but customer creation returned HTTP 500; the oracle returned HTTP 201 with `status=active`. Chromium then rendered all active customer statuses after creation. Fixture SHA-256: `30a2c232434af3c56b7f5494be7186194d323f6514b7d611be059ae9e4b7ea0b`.

Result: **PASS**.
