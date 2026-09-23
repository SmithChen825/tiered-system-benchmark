# Task L4-03: Restore service startup and dashboard health

The database and frontend containers start, but the API does not become healthy and the system dashboard reports that it is unavailable. Restore the existing three-service application so all Compose health checks pass and the dashboard loads its current PostgreSQL-backed status and metrics. Preserve the service names, ports, database schema and seed values, API routes, frontend/backend separation, CORS boundary, and startup database check. Do not bypass database connectivity or replace it with hard-coded health data.

