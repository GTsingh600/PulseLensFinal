"""Explainer key coverage (M1.3): every key the code, the check registry or policy.yaml uses must exist in
docs/EXPLAINERS.md; keys nobody uses are listed (not an error: many belong to checks still to be built).

    python scripts/check_explainers.py          # exit 1 when a key is missing
    python scripts/check_explainers.py --unused # also list unused keys

Keys are found as string literals with a known prefix (`"check.optical.face_neck"`, `'prompt.light'`). Keys built
at run time (f"check.{id}") are not seen here, so the registry is checked directly. Event type names that share a
prefix (check.result, plan.decided, stage.changed) and WebSocket message types (stage.done) are skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
import typing
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

PREFIXES = (
    "stage",
    "field",
    "check",
    "plan",
    "family",
    "outcome",
    "status",
    "plot",
    "results",
    "prompt",
    "notice",
    "consent",
)
LITERAL = re.compile(r"""["'`]((?:""" + "|".join(PREFIXES) + r""")\.[A-Za-z0-9_.]+)["'`]""")
SOURCE_GLOBS = (
    "server/pulselens/**/*.py",
    "packages/*/src/**/*.ts",
    "packages/*/src/**/*.tsx",
    "apps/*/src/**/*.ts",
    "apps/*/src/**/*.tsx",
)
SKIP = re.compile(r"(\.test\.tsx?$|\.gen\.ts$|[\\/]tests?[\\/])")
POLICY = ROOT / "server/pulselens/planner/policy.yaml"
HEADING = re.compile(r"^###\s+(\S+)\s*$", re.M)


def explainer_keys(markdown: str) -> set[str]:
    return set(HEADING.findall(markdown))


def protocol_names() -> set[str]:
    """Event types and WebSocket message types (stage.done, ...): dotted names that are not explainer keys."""
    from pulselens import models

    names = set(typing.get_args(models.EventType))
    for model in models.EXPORTED_MODELS:
        field = model.model_fields.get("type")
        if field is not None and isinstance(field.default, str):
            names.add(field.default)
    return names


def keys_in_sources(root: Path, globs: Iterable[str] = SOURCE_GLOBS) -> dict[str, set[str]]:
    """{key: files that mention it} for key-shaped string literals, event types excluded."""
    found: dict[str, set[str]] = {}
    skip = protocol_names()
    for pattern in globs:
        for path in root.glob(pattern):
            rel = path.relative_to(root).as_posix()
            if SKIP.search(rel):
                continue
            for key in LITERAL.findall(path.read_text(encoding="utf-8", errors="replace")):
                key = key.rstrip(".")
                if key not in skip:
                    found.setdefault(key, set()).add(rel)
    return found


def keys_in_registry() -> dict[str, set[str]]:
    from pulselens.planner.registry import load_all

    found: dict[str, set[str]] = {}
    for check_id, (spec, _run) in load_all().items():
        for key in {spec.explainer, f"check.{check_id}"}:
            found.setdefault(key, set()).add(f"registry:{check_id}")
    return found


def keys_in_policy(path: Path = POLICY) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    import yaml

    found: dict[str, set[str]] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and LITERAL.fullmatch(f'"{node}"'):
            found.setdefault(node, set()).add(path.name)

    walk(yaml.safe_load(path.read_text(encoding="utf-8")))
    return found


@dataclass
class Coverage:
    missing: dict[str, set[str]]  # used but not in EXPLAINERS.md -> where
    unused: list[str]  # in EXPLAINERS.md, used nowhere


def coverage(markdown: str, *sources: dict[str, set[str]]) -> Coverage:
    defined = explainer_keys(markdown)
    used: dict[str, set[str]] = {}
    for s in sources:
        for k, where in s.items():
            used.setdefault(k, set()).update(where)
    return Coverage(
        missing={k: v for k, v in sorted(used.items()) if k not in defined},
        unused=sorted(defined - used.keys()),
    )


def repo_coverage() -> Coverage:
    md = (ROOT / "docs/EXPLAINERS.md").read_text(encoding="utf-8")
    return coverage(md, keys_in_sources(ROOT), keys_in_registry(), keys_in_policy())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unused", action="store_true", help="list keys in EXPLAINERS.md that nothing uses yet")
    args = ap.parse_args()
    cov = repo_coverage()
    for key, where in cov.missing.items():
        print(f"MISSING {key}  (used in {', '.join(sorted(where))})")
    if args.unused:
        print(f"{len(cov.unused)} unused key(s): {', '.join(cov.unused)}")
    print(f"{len(cov.missing)} missing key(s)")
    return 1 if cov.missing else 0


if __name__ == "__main__":
    sys.exit(main())
