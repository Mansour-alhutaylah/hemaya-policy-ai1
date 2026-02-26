"""Quick DB connection test — run from project root: python test_db_connection.py"""
import os
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL", "")
print(f"DATABASE_URL loaded: {'YES' if db_url else 'NO'}")
if db_url:
    # Show only the end so password is hidden
    print(f"  URL ends with: ...{db_url[-40:]}")

print("\nTrying to connect (timeout = 10 seconds)...")

try:
    import psycopg2
    # Parse the URL manually for psycopg2
    from urllib.parse import urlparse, unquote
    parsed = urlparse(db_url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        connect_timeout=10,
        sslmode="require",
    )
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"\n✅ SUCCESS! Connected to PostgreSQL.")
    print(f"   Version: {version[:60]}")

except psycopg2.OperationalError as e:
    print(f"\n❌ CONNECTION FAILED: {e}")
    print("\nThis means Supabase is not reachable. Most likely causes:")
    print("  1. Your Supabase project is PAUSED — go to supabase.com/dashboard and unpause it")
    print("  2. Wrong DATABASE_URL in .env")
    print("  3. Network/firewall blocking the connection")

except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}: {e}")
