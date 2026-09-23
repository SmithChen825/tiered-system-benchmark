CREATE TABLE dashboard_metrics (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL CHECK (value >= 0),
    display_order INTEGER NOT NULL UNIQUE
);

INSERT INTO dashboard_metrics (name, value, display_order) VALUES
    ('Jobs processed', 128, 1),
    ('Active workers', 4, 2),
    ('Pending alerts', 0, 3);

