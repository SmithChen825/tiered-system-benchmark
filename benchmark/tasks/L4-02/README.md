# L4-02 Required Customer Status

Deterministic Level 4 task: PostgreSQL contains a required `customers.status` field, but the ORM, Pydantic request/response contracts, and create mapping were not updated. The oracle adds the frozen `active` default at the API boundary and persists it through the ORM.
