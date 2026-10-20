"""config.yaml (SPEC 18) and the secrets in .env (CLAUDE.md rule 8)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# server/pulselens/config.py -> repo root. PULSE_ROOT overrides it (tests, a copy of data/ for the purge script).
REPO_ROOT = Path(os.environ.get("PULSE_ROOT") or Path(__file__).resolve().parents[2])
CONFIG_PATH = REPO_ROOT / "config.yaml"
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = REPO_ROOT / "models"


@lru_cache
def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def config_hash() -> str:
    """sha256 of config.yaml as stored; freeze.py records it and run.py compares it (SPEC 16)."""
    return hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


@dataclass(frozen=True)
class Settings:
    pulse_hmac_secret: str
    console_passcode: str
    team_codes: tuple[str, ...]

    @property
    def uses_placeholders(self) -> bool:
        return "change-me" in (self.pulse_hmac_secret, self.console_passcode)


@lru_cache
def get_settings() -> Settings:
    """Real environment variables win over .env."""
    env = {**_read_dotenv(REPO_ROOT / ".env"), **os.environ}
    return Settings(
        pulse_hmac_secret=env.get("PULSE_HMAC_SECRET", "change-me"),
        console_passcode=env.get("CONSOLE_PASSCODE", "change-me"),
        team_codes=tuple(c.strip() for c in env.get("TEAM_CODES", "").split(",") if c.strip()),
    )
