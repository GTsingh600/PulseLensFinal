from pulselens.config import config_hash, load_config

# Top-level sections and a few values pinned by SPEC 18; other code reads these keys directly.
SPEC_SECTIONS = {
    "capture",
    "probe",
    "pulses",
    "profiles",
    "planner",
    "calibration",
    "continuity",
    "quality",
    "physiology",
    "demo",
}


def test_config_has_every_spec_section() -> None:
    assert set(load_config()) == SPEC_SECTIONS


def test_config_values_match_spec() -> None:
    c = load_config()
    assert c["capture"]["fp_every"] == 5
    assert c["probe"]["modes"] == [[1280, 720, 30], [640, 480, 30], [1000, 750, 24]]
    light = c["pulses"]["light"]
    assert (light["colour"], light["split"], light["white"]) == (6, 2, 2)
    assert light["luminance_tolerance"] == 0.05
    assert c["planner"]["effort_cap"] == 20
    assert c["calibration"]["provisional_tau"] == 3.0
    assert c["quality"]["min"] == 0.5
    assert c["physiology"]["enabled"] is False
    assert c["demo"]["pair_code_ttl_min"] == 10


def test_config_hash_is_stable() -> None:
    assert config_hash() == config_hash()
    assert len(config_hash()) == 64
