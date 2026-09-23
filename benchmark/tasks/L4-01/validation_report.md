# L4-01 Validation Report

- Validation date: 2026-08-06
- Host platform: Windows with Docker Desktop 29.2.1
- Database: PostgreSQL 16.6 Alpine, digest pinned
- Backend: Python 3.12.8 container, FastAPI 0.115.6, SQLAlchemy 2.0.36, psycopg 3.2.3
- Frontend: Vue 3.5.13, Vite 6.4.3, Node 22.12.0
- Browser evaluator: Playwright 1.62.0 with installed Google Chrome
- Fixture SHA-256: `75b862c9908d5acff9a669dd7c38135bddbee140344123130bb24cf7741d1915`
- Frontend lockfile SHA-256: `5a5c529266cd8fd63207e49a659d7ba8fa1fea92dbc7a20fc95487e0f487dbf1`
- `npm audit`: zero known vulnerabilities at validation time

## Contract and reset checks

1. Both agent-visible backend smoke tests pass in the faulty fixture.
2. The first fresh reset fails exactly three downstream-reference checks:
   - SQLAlchemy `User.age` mapping;
   - Pydantic `UserRead.age` field;
   - Vue `Age` header and `user.age` cell.
3. The database initialization SQL contains no `age` column or rollback operation.
4. The oracle passes all six evaluator-only source and architecture checks.
5. A second reset reproduces the same fixture hash and the same three failures.
6. The multi-file `oracle/oracle.patch` passes `git apply --check`.

## Three-service Compose evidence

Baseline:

```text
backend health: PASS
database columns: id,name,email,role
users.age column count: 0
seeded user rows: 3
GET /api/users: HTTP 500
browser error visible: true
browser table visible: false
```

Oracle:

```text
backend health: PASS
database columns: id,name,email,role
users.age column count: 0
seeded user rows: 3
GET /api/users: HTTP 200
API fields: id,name,email,role
browser error visible: false
browser table visible: true
browser row count: 3
browser headers: Name,Email,Role
browser console errors: 0
```

The database volume was removed between baseline and oracle validation, proving that both runs begin from the same fresh post-migration schema.

## Result

```text
L4-01 contract/reset validation: PASS
L4-01 Compose/PostgreSQL/API/Chromium validation: PASS
```

The implementation is suitable for the representative pilot baseline. It does not enter the final experiment freeze until the four-system pilot, built-image IDs, system configurations, limits, and complete freeze manifest are approved.
