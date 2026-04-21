import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool


load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Add it to your .env file.")

# Supabase / PostgreSQL connection
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,       # detect stale connections
    poolclass=NullPool,
    connect_args={"connect_timeout": 10},  # fail after 10s if TCP hangs
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
