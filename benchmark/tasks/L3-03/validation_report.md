# L3-03 Validation Report

Validated 2026-08-29. Both fresh resets failed exactly `test_frontend_targets_the_current_password_reset_endpoint`. The researcher-authored oracle changed only the Vue endpoint from `/api/v1/auth/password-reset` to `/api/v2/auth/password-reset` and passed all six hidden checks.

Separate baseline and oracle Compose stacks passed health and direct API checks: the current v2 endpoint returned the frozen HTTP 202 response and the retired v1 route returned HTTP 404. In baseline Chromium, submitting `maya@example.test` sent a direct POST to the backend v1 URL, received 404, and rendered `Unable to submit password reset.` In oracle Chromium, the same form sent a direct POST to the backend v2 URL, received 202, and rendered the API-derived confirmation. No frontend proxy was introduced. Fixture SHA-256: `63308a764506427670ed11e857b54fd5f45149a80c29cf666f0843366b10ffbd`.

Result: **PASS**.

