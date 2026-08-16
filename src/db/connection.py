"""Database connection factory."""

import psycopg2
from src.core.config import PostgresSettings

def get_connection(settings: PostgresSettings):
    """Create and return a new PostgreSQL connection."""
    connect_kwargs = dict(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        dbname=settings.dbname,
    )
    if settings.sslmode and settings.sslmode != "disable":
        connect_kwargs["sslmode"] = settings.sslmode
    return psycopg2.connect(**connect_kwargs)
