# Task L4-02: Restore customer creation after the schema change

The customer directory and its two existing records load, but creating a new customer without a status fails. New customers must default to `active`; the only permitted status values are `active` and `inactive`. Restore creation and subsequent reads while preserving the existing records, unique email rule, three-service architecture, and required PostgreSQL `customers.status` column.
