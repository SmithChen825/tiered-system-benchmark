# Task catalogue

Each linked task directory contains its public brief, faulty fixture, evaluator, oracle, and validation notes.

| Task | Architecture | Public objective |
|---|---|---|
| [L1-01](../benchmark/tasks/L1-01) | Nginx-served static HTML/CSS/SVG website | Restore the missing images in all product cards. |
| [L1-02](../benchmark/tasks/L1-02) | Nginx-served static HTML/CSS website | Make the existing navigation usable at mobile width. |
| [L1-03](../benchmark/tasks/L1-03) | Nginx-served static HTML/CSS/JavaScript website | Restore the existing contact-form client-side validation and valid-submission confirmation. |
| [L2-01](../benchmark/tasks/L2-01) | Single-service FastAPI application | Restore the item-detail page. |
| [L2-02](../benchmark/tasks/L2-02) | single-service FastAPI application with SQLite persistence | Restore creation of a new task from the web form. |
| [L2-03](../benchmark/tasks/L2-03) | Single-service FastAPI application with JSON file persistence | Repair import and export of saved notes, including persistence after service restart. |
| [L3-01](../benchmark/tasks/L3-01) | Vue 3 frontend and FastAPI backend in separate containers | Restore the frontend's ability to load account data from the backend. |
| [L3-02](../benchmark/tasks/L3-02) | Vue frontend plus FastAPI backend | Restore the order-status panel. |
| [L3-03](../benchmark/tasks/L3-03) | Vue frontend plus FastAPI backend | Restore password-reset submission from the Vue frontend to the current FastAPI endpoint. |
| [L4-01](../benchmark/tasks/L4-01) | Vue 3 frontend, FastAPI/SQLAlchemy backend, and PostgreSQL database | Complete the breaking removal of users.age across all downstream layers. |
| [L4-02](../benchmark/tasks/L4-02) | Vue frontend, FastAPI/SQLAlchemy backend, PostgreSQL database | Restore creation of a customer record after a schema change. |
| [L4-03](../benchmark/tasks/L4-03) | Vue frontend, FastAPI/SQLAlchemy backend, PostgreSQL database | Restore API startup and the PostgreSQL-backed system dashboard health check. |
