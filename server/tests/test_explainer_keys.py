"""M1.3 acceptance: a test fails if any key referenced in code, the check registry or policy.yaml is missing from
EXPLAINERS.md, and the reverse check lists unused keys."""

import importlib.util
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_explainers", ROOT / "scripts/check_explainers.py")
assert spec and spec.loader
ck = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ck  # dataclasses look their module up here
spec.loader.exec_module(ck)


def test_every_key_used_by_code_registry_or_policy_exists() -> None:
    cov = ck.repo_coverage()
    report = "\n".join(f"{k} (used in {', '.join(sorted(w))})" for k, w in cov.missing.items())
    assert not cov.missing, f"Add these keys to docs/EXPLAINERS.md, then run `make explainers`:\n{report}"


def test_the_reverse_check_lists_unused_keys() -> None:
    cov = ck.repo_coverage()
    assert isinstance(cov.unused, list) and cov.unused == sorted(cov.unused)
    if cov.unused:
        warnings.warn(f"{len(cov.unused)} explainer key(s) not used yet: {', '.join(cov.unused)}", stacklevel=1)


def test_the_checker_finds_missing_and_unused_keys(tmp_path: Path) -> None:
    md = "### stage.camera\n- title: Camera\n\n### prompt.light\n- text: Look\n\n### field.gyro\n- text: Gyro\n"
    (tmp_path / "server/pulselens").mkdir(parents=True)
    (tmp_path / "apps/lab/src").mkdir(parents=True)
    (tmp_path / "server/pulselens/x.py").write_text(
        'send(StageMessage(prompt="prompt.light"))\nemit("stage.changed", {})\n'
    )
    (tmp_path / "apps/lab/src/A.tsx").write_text('explain("stage.camera"); explain(`check.optical.face_neck`);\n')
    (tmp_path / "apps/lab/src/A.test.tsx").write_text('explain("check.not.counted.in.tests")\n')
    policy = tmp_path / "policy.yaml"
    policy.write_text("units:\n  tilt: {reason: plan.reason.tilt_gyro, family: motion}\n")

    cov = ck.coverage(md, ck.keys_in_sources(tmp_path), ck.keys_in_policy(policy))
    assert set(cov.missing) == {"check.optical.face_neck", "plan.reason.tilt_gyro"}  # stage.changed is an event type
    assert cov.missing["plan.reason.tilt_gyro"] == {"policy.yaml"}
    assert cov.unused == ["field.gyro"]


def test_registered_checks_need_their_explainer() -> None:
    reg = ck.keys_in_registry()
    assert "check.optical.face_neck" in reg and "check.optical.light.delay" in reg
    md = "### check.optical.light.delay\n- title: x\n"
    assert "check.optical.face_neck" in ck.coverage(md, reg).missing
