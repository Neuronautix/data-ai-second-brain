from app.normalize_kb import normalize_kb
from pathlib import Path


if __name__ == "__main__":
    normalize_kb(Path("data/kb/kb.json"), Path("data/kb/kb.json"), Path("data/kb/kb.sqlite"))
