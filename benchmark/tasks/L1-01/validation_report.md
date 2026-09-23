# L1-01 Validation Report

- Validation date: 2026-08-06
- Host platform: Windows
- Python: 3.12.13
- Browser evaluator: Playwright 1.62.0 with installed Google Chrome
- Nginx implementation image: `nginx:1.27.3-alpine@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4`
- Fixture SHA-256: `4311c7ab44139ad55dbbf94e3680ee3b30c7dbc165df2f442e7edc7c76f21b47`

## Checks completed

1. Researcher-facing JSON and Python files parse successfully.
2. Both agent-visible structural smoke tests pass in the faulty fixture.
3. The first fresh reset fails exactly the two intended evaluator-only filesystem checks.
4. A real headless Chromium page load observes three product images, all broken in the faulty fixture.
5. The researcher-authored oracle passes all six Python hidden tests.
6. The oracle page passes the Chromium check with three loaded images, zero broken images, and zero failed image responses.
7. A second independent reset reproduces the same fixture hash, Python failures, and three broken browser images.
8. `oracle/oracle.patch` passes `git apply --check` against the faulty fixture.
9. The pinned Nginx 1.27.3 baseline container returns HTTP 200 for the page, HTTP 404 for all three stale paths, and HTTP 200 for the three supplied asset paths.
10. The pinned oracle container passes a real Chromium load with three rendered images, no broken images, and no failed image responses.

## Result

```text
L1-01 validation cycle: PASS
baseline pytest failures: 2 expected
baseline Chromium broken images: 3 expected
oracle Python evaluator: PASS
oracle Chromium evaluator: PASS
second reset same failure: PASS
baseline Nginx container: PASS
oracle Nginx + Chromium: PASS
```

The task implementation and container behaviour are validated. It does not enter the final experiment freeze until the broader four-system pilot and experiment-freeze manifest are complete.
