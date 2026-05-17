import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


def load_environment():
    for path in [ROOT.parent / ".env", ROOT / ".env"]:
        if path.exists():
            load_dotenv(path, override=False)

    aliases = {
        "agent_phone_api_key": "AGENT_PHONE_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "moss_api_key": "MOSS_PROJECT_ID",
        "moss_project_key": "MOSS_PROJECT_KEY",
    }
    for source, target in aliases.items():
        if not os.getenv(target) and os.getenv(source):
            os.environ[target] = os.getenv(source, "").strip()


def truthy(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


load_environment()
