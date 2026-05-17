import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_json(name):
    with open(DATA_DIR / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(name, value):
    with open(DATA_DIR / name, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
