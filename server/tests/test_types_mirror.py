"""packages/types must mirror models.py and config.yaml exactly (CLAUDE.md: models.py is the source of truth)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gen_types", ROOT / "scripts/gen_types.py")
assert spec and spec.loader
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


@pytest.mark.parametrize("name", sorted(gen.OUTPUTS))
def test_ts_mirror_is_up_to_date(name: str) -> None:
    current = (gen.OUT_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == gen.OUTPUTS[name](), f"packages/types/src/{name} is stale: run `make types` and commit it"
