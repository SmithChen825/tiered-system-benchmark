# L3-01 Validation Report

- Validation date: 2026-08-08
- Host platform: Windows with Docker Desktop 29.2.1
- Python evaluator: Python 3.12.8 container, pytest 8.3.4
- Frontend: Vue 3.5.13, Vite 6.4.3, Node 22.12.0
- Browser evaluator: Playwright 1.62.0 with installed Google Chrome
- Fixture SHA-256: `f85a274f8e1ff9ffd05df79a441a65ff0076fb559d3850e0e12f6749284d7b52`
- Frontend lockfile SHA-256: `acfdf7dcafe25f3fbe73c7acc96f53a124b099fcfea8fb4dc58487bf27c5fcdd`
- `npm audit`: zero known vulnerabilities at validation time

## Contract and reset checks

1. The two agent-visible direct API smoke tests pass in the faulty fixture.
2. The first fresh reset fails exactly four evaluator-only CORS checks:
   - expected-origin GET response header;
   - expected-origin preflight;
   - frozen named-origin policy;
   - rejection of the stale development origin.
3. The oracle passes all eight evaluator-only hidden tests in the 2026-08-08 validation suite.
4. A second independent reset reproduces the same fixture hash and the same four failures.
5. `oracle/oracle.patch` passes `git apply --check` against the faulty fixture.

## Compose and real-browser checks

The baseline and oracle were each built and run as separate Vue/Nginx and FastAPI services.

Baseline evidence:

```text
backend health: PASS
direct account endpoint: PASS
Access-Control-Allow-Origin for http://127.0.0.1:8080: absent
preflight status: 400
browser error visible: true
browser account card visible: false
```

Oracle evidence:

```text
backend health: PASS
direct account endpoint: PASS
Access-Control-Allow-Origin: http://127.0.0.1:8080
preflight status: 200
browser error visible: false
browser account card visible: true
account name: Ada Lovelace
account role: Platform Engineer
browser console errors: 0
```

## Result

```text
L3-01 contract/reset validation: PASS
L3-01 Compose validation: PASS
```

The implementation is suitable for the representative pilot baseline. It does not enter the final experiment freeze until the four-system pilot, built-image IDs, system configurations, limits, and complete freeze manifest are approved.

## Evaluator-classification addendum (2026-08-08)

The approved evaluator manifest maps four functional tests and seven architectural
invariants separately. One static hidden check was added to verify that frontend
and backend remain separate Compose services. The complete reset/oracle hidden-test
cycle and the baseline/oracle Compose, CORS, API, and real-Chrome checks were rerun
successfully on 2026-08-08. The post-change revalidation gate is therefore cleared.
