# Task L4-01: Complete removal of `users.age`

A database migration has intentionally removed the `age` column from the `users` table, but the user directory no longer loads. Complete the downstream repair across the backend and frontend so that the user list works again.

The `users.age` column must remain absent. Restoring the column, rolling back the migration, substituting a default age, or hiding the failure without repairing downstream contracts is not acceptable. Preserve the remaining user data and the existing three-service architecture.

Work only within the supplied repository. Diagnose and repair the fault, run the available relevant tests, and verify the database, API, and browser behaviour before submitting the final state. Do not modify tests to obtain a passing result.
