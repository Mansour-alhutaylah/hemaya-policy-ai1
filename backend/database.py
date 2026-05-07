import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool


load_dotenv()

_raw_url = os.getenv("DATABASE_URL")

if not _raw_url:
    raise RuntimeError("DATABASE_URL environment variable is not set. Add it to your .env file.")

# SQLAlchemy 2.x removed the legacy 'postgres://' dialect alias that older
# Supabase / Heroku / Render connection strings still use. Normalise it here
# so the server starts regardless of which prefix the host provides.
SQLALCHEMY_DATABASE_URL = _raw_url.replace("postgres://", "postgresql://", 1)

# Build connect_args. Supabase (and most managed PG hosts) require TLS, so
# we inject sslmode=require only when the URL doesn't already carry it.
_connect_args: dict = {"connect_timeout": 30}
if "sslmode" not in SQLALCHEMY_DATABASE_URL:
    _connect_args["sslmode"] = "require"

# NullPool: never hold idle connections — critical for Supabase's connection
# limit on free-tier projects. pool_pre_ping is omitted because it is a no-op
# with NullPool in SQLAlchemy 2.x (there is no pooled connection to ping).
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=NullPool,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
