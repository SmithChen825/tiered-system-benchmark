import os

from sqlalchemy import create_engine


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://benchmark:benchmark@db:5432/benchmark",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

