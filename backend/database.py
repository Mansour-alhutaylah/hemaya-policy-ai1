import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool


load_dotenv()

_raw_url = os.getenv("DATABASE_URL")

if not _raw_url:
    raise RuntimeError("DATABASE_URL environment variable is not set. Add it to your .env file.")

# Normalise legacy 'postgres://' prefix (Supabase / Heroku / Render).
SQLALCHEMY_DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1)

# Inject sslmode=require when the URL doesn't already carry it.
_connect_args: dict = {"connect_timeout": 30}
if "sslmode" not in SQLALCHEMY_DATABASE_URL:
    _connect_args["sslmode"] = "require"

# Pool strategy — auto-detected from the port in DATABASE_URL:
#
#   :6543  →  Supabase PgBouncer pooler (transaction or session mode).
#             PgBouncer already manages its own pool.  SQLAlchemy must use
#             NullPool so it does not hold connections the pooler has released.
#
#   :5432  →  Direct PostgreSQL connection.
#   other  →  Unknown host/port; treat as direct and use a conservative pool.
#
# QueuePool settings for direct connections:
#   pool_size=3       — 3 always-open connections (covers normal request load)
#   max_overflow=5    — up to 8 total under burst (API + 1 analysis job)
#   pool_recycle=300  — recycle before Supabase's 300 s idle-connection timeout
#   pool_pre_ping     — discard stale connections silently on checkout
#
_is_pooler = ":6543" in SQLALCHEMY_DATABASE_URL

if _is_pooler:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=NullPool,
        connect_args=_connect_args,
    )
    print("[db] Using NullPool (Supabase pooler port 6543 detected)")
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=QueuePool,
        pool_size=3,
        max_overflow=5,
        pool_recycle=300,
        pool_pre_ping=True,
        connect_args=_connect_args,
    )
    print("[db] Using QueuePool(3+5, recycle=300s) (direct connection)")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_user_context(db: Session, user_id: str) -> None:
    """Set the current user's UUID as a session-local variable so RLS policies
    can reference it via current_setting('app.current_user_id', true).

    Call this once per authenticated request, right after resolving the user.
    SET LOCAL persists for the lifetime of the current transaction, which maps
    to the lifetime of a single FastAPI request with autocommit=False.
    """
    db.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": str(user_id)})
