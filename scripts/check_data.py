"""Market data provider diagnostic check."""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from indigo_quant.db.session import SessionLocal
from indigo_quant.data.ingestion import DataIngestionEngine

if __name__ == "__main__":
    db = SessionLocal()
    engine = DataIngestionEngine(db)
    health = engine.get_provider_health()
    print("Market Data Provider Health Status:")
    for prov, status in health.items():
        print(f"  • {prov.upper()}: {'HEALTHY' if status else 'UNREACHABLE'}")
    db.close()
