"""DB gateway (V2). Any service that needs Postgres gets its session here.

# ponytail: thin gateway — it only hands out sessions; each service keeps its
# own queries (no repository layer). FastAPI routes still use app.database.get_db;
# this is the seam for service code that runs outside a request (scripts, jobs).
"""
from app.database import SessionLocal


def get_session():
    """A new AsyncSession for callers outside FastAPI's dependency injection."""
    return SessionLocal()
