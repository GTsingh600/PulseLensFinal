"""packages/types must mirror models.py exactly (CLAUDE.md: models.py is the source of truth)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ts_mirror_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location("gen_types", ROOT / "scripts/gen_types.py")
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    current = gen.OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == gen.render(), "packages/types is stale: run `make types` and commit the result"
