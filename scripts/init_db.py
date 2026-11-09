"""Database initialization script."""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add src to pythonpath
src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from indigo_quant.db.session import SessionLocal
from indigo_quant.db.repository import init_db, seed_universe_and_accounts

if __name__ == "__main__":
    print("Initializing Indigo Quant Database...")
    init_db()
    db = SessionLocal()
    seed_universe_and_accounts(db)
    db.close()
    print("Database initialization and initial seeding complete.")
