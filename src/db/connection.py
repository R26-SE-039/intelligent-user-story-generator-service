"""Database connection factory."""

import psycopg2
from src.core.config import PostgresSettings

def get_connection(settings: PostgresSettings):
    """Create and return a new PostgreSQL connection."""
    return psycopg2.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        dbname=settings.dbname,
    )
