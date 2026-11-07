"""Compatibility registry (Milestone 5, workstream F): schema, level derivation, refusals,
staleness check, live status and ``GET /api/v1/compatibility``.

Each derivation rule (R1-R7, backend/src/brainos/compat/rules.py) has at least one malformed or
over-claiming input that is refused or not counted. Inputs are built in a temporary repository;
certify reports are the real committed ones, copied and (for the malformed cases) altered.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient

from brainos import __version__
from brainos.compat.build import (
    BEGIN,
    DOC,
    END,
    REGISTRY,
    REPO_ROOT,
    SCHEMA,
    SOURCES,
    build,
    main,
    registry_schema,
    stale,
)
from brainos.compat.live import InstalledPlugin, builtin_status, live_status, plugin_status
from brainos.compat.model import LEVELS, CertifyInfo, Evidence, Registry
from brainos.compat.rules import CompatError, certify_problems, derive_level
from brainos.server import create_app

from .conftest import make_settings

REPORTS = REPO_ROOT / "docs" / "compatibility"
EXAMPLE_REPORT = "example-mi-eeg.certify.json"
BRAINFLOW_REPORT = "brainflow-synthetic.certify.json"
EXAMPLE_PKG = REPO_ROOT / "examples" / "adapters" / "brainos-example-adapter"


# ----------------------------------------------------------------------------- helpers


def report(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((REPORTS / name).read_text(encoding="utf-8"))
    return doc


def curated_test(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "test",
        "path": "tests/test_demo.py",
        "description": "Demo adapter unit tests.",
        "date": "2026-11-07",
        "anchor": "def test_demo",
        "runs_in_ci": True,
    }
    item.update(over)
    return item


def builtin(**over: Any) -> dict[str, Any]:
    b: dict[str, Any] = {
        "id": "brainos.demo",
        "kind": "builtin_adapter",
        "display_name": "Demo adapter",
        "code": "src/demo.py",
        "protocol": "In-process demo protocol",
        "read_only": {"statement": "Receive-only demo adapter.", "verified_by": []},
        "evidence": [curated_test()],
        "not_tested": ["Hardware."],
        "limitations": [],
    }
    b.update(over)
    return b


def example_plugin(**over: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "package": "brainos-example-adapter",
        "source_dir": "plugins/example",
        "protocol": "Adapter SDK plugin (synthetic)",
        "read_only": {"statement": "Receive-only plugin in its own process.", "verified_by": []},
        "evidence": [],
        "not_tested": ["Hardware."],
        "limitations": [],
    }
    p.update(over)
    return p


class TmpRepo:
    """A minimal checkout the builder can read."""

    def __init__(self, root: Path) -> None:
        self.root = root
        for d in ("docs/compatibility", "compat", "backend", "src", "tests"):
            (root / d).mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / "docs/VALIDATION_LEVELS.md", root / "docs/VALIDATION_LEVELS.md")
        self.write("backend/pyproject.toml", '[project]\nname = "brainos"\nversion = "0.3.0"\n')
        self.write(DOC, f"# Compatibility\n\nHand-written text.\n\n{BEGIN}\n{END}\n\nAfter.\n")
        self.write("src/demo.py", 'ADAPTER = "brainos.demo@0.1.0"\nKIND = Modality.EEG\n')
        self.write(
            "tests/test_demo.py", "def test_demo() -> None:\n    pass  # pylsl.StreamOutlet\n"
        )
        self.write("docs/RUNS.md", "The opt-in test passed here on 2026-11-07.\n")
        self.sources(builtins=[builtin()], plugins=[])

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def sources(self, *, builtins: list[dict[str, Any]], plugins: list[dict[str, Any]]) -> None:
        self.write(
            SOURCES,
            json.dumps({"sources_version": "1.0", "builtins": builtins, "plugins": plugins}),
        )

    def report(self, name: str, doc: dict[str, Any]) -> None:
        self.write(f"docs/compatibility/{name}", json.dumps(doc))

    def example_package(self) -> None:
        """The example plugin's real pyproject and source at plugins/example."""
        dest = self.root / "plugins/example"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(EXAMPLE_PKG / "pyproject.toml", dest / "pyproject.toml")
        shutil.copytree(
            EXAMPLE_PKG / "src",
            dest / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )

    def build(self) -> Registry:
        return build(self.root).registry

    def entry(self, entry_id: str) -> Any:
        return next(e for e in self.build().entries if e.id == entry_id)


@pytest.fixture
def repo(tmp_path: Path) -> TmpRepo:
    return TmpRepo(tmp_path / "repo")


def refused(repo: TmpRepo, match: str) -> None:
    with pytest.raises(CompatError, match=match):
        repo.build()


# ------------------------------------------------------------------- the committed registry


def test_committed_registry_is_current() -> None:
    """What CI runs: the committed registry, schema and docs section equal a fresh build."""
    outputs = build(REPO_ROOT)
    assert stale(REPO_ROOT, outputs) == []
    assert main(["--check"]) == 0


def test_committed_registry_matches_its_schema() -> None:
    data = json.loads((REPO_ROOT / REGISTRY).read_text(encoding="utf-8"))
    schema = json.loads((REPO_ROOT / SCHEMA).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(data))
    assert errors == []
    reg = Registry.model_validate(data)
    assert [d.id for d in reg.levels] == list(LEVELS)


def test_committed_registry_claims_no_hardware_or_human_level() -> None:
    reg = Registry.model_validate_json((REPO_ROOT / REGISTRY).read_bytes())
    assert reg.summary["hardware_verified"] == 0 and reg.summary["human_validated"] == 0
    assert all(e.level not in ("hardware_verified", "human_validated") for e in reg.entries)
    assert "No entry has reached hardware_verified (level 3) or human_validated" in reg.notice
    by_id = {e.id: e for e in reg.entries}
    expected = {
        "brainos.sim.profile_a",
        "brainos.sim.profile_b",
        "brainos.replay",
        "brainos.nwb.units",
        "brainos.nwb.ecog",
        "brainos.cursorclick.t15",
        "brainos.lsl",
        "brainos.openephys.zmq",
        "brainos-example-adapter",
        "brainos-brainflow",
        "brainos-bci2000",
    }
    assert set(by_id) == expected
    for sim in ("brainos.sim.profile_a", "brainos.sim.profile_b"):
        assert by_id[sim].synthetic_only and by_id[sim].level == "software_implemented"
    for e in reg.entries:
        assert e.level is not None or not e.in_checkout, e.id
        for x in e.evidence:  # every path the registry cites exists in this checkout
            assert (REPO_ROOT / x.path).is_file(), x.path
            if x.certify is not None:  # R5: a report counts only for this checkout's plugin
                assert x.counted == (x.certify.source_matches is not False), x.path


# ------------------------------------------------------------------- schema and structure


def test_minimal_repo_builds_and_validates(repo: TmpRepo) -> None:
    outputs = build(repo.root)
    data = json.loads(outputs.files[REGISTRY])
    assert list(jsonschema.Draft202012Validator(registry_schema()).iter_errors(data)) == []
    (e,) = outputs.registry.entries
    assert e.id == "brainos.demo" and e.version == "0.3.0" and e.package == "brainos"
    assert e.level == "software_implemented" and e.level_number == 1
    assert e.module is None  # code outside backend/src
    doc = outputs.files[DOC]
    assert doc.startswith("# Compatibility\n\nHand-written text.") and doc.endswith("After.\n")
    assert "| Demo adapter (`brainos.demo`) | built-in adapter | brainos 0.3.0 |" in doc


def test_r6_typed_in_level_is_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(level="protocol_tested")], plugins=[])
    refused(repo, "levels are derived from evidence, never typed in")


def test_r6_unknown_evidence_field_is_refused(repo: TmpRepo) -> None:
    repo.sources(
        builtins=[builtin(evidence=[curated_test(supports="protocol_tested")])], plugins=[]
    )
    refused(repo, "Extra inputs are not permitted")


def test_r6_duplicate_ids_are_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(), builtin()], plugins=[])
    refused(repo, "duplicate ids")


def test_r6_missing_evidence_path_is_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(evidence=[curated_test(path="tests/test_gone.py")])], plugins=[])
    refused(repo, "evidence path does not exist")


def test_r6_anchor_not_in_file_is_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(evidence=[curated_test(anchor="not in there")])], plugins=[])
    refused(repo, "anchor 'not in there' not found")


def test_r6_path_leaving_the_repository_is_refused(repo: TmpRepo) -> None:
    repo.sources(
        builtins=[builtin(evidence=[curated_test(path="tests/../../x/test_a.py")])], plugins=[]
    )
    refused(repo, "leaves the repository")


def test_r6_adapter_id_must_appear_in_its_code(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(id="brainos.other")], plugins=[])
    refused(repo, "does not appear in src/demo.py")


def test_r6_declared_modality_must_be_used_by_the_code(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(modalities_declared=["eeg"])], plugins=[])
    assert repo.entry("brainos.demo").modalities_declared == ["eeg"]
    repo.sources(builtins=[builtin(modalities_declared=["intracortical"])], plugins=[])
    refused(repo, "declares modality 'intracortical'")


def test_r6_future_date_is_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(evidence=[curated_test(date="2999-01-01")])], plugins=[])
    refused(repo, "in the future")


def test_code_not_in_checkout_is_listed_without_level(repo: TmpRepo) -> None:
    repo.sources(
        builtins=[builtin(code="src/absent", evidence=[curated_test(path="tests/test_absent.py")])],
        plugins=[],
    )
    e = repo.entry("brainos.demo")
    assert not e.in_checkout and e.level is None and e.evidence == []
    assert e.level_basis[0].startswith("not in this checkout")


# ------------------------------------------------------------------- R1 software_implemented


def test_r1_no_evidence_means_no_level(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(evidence=[])], plugins=[])
    e = repo.entry("brainos.demo")
    assert e.level is None and e.level_number is None
    assert e.level_basis[0] == (
        "software_implemented (R1): not reached: no counted test or certify report"
    )


def test_r1_docs_and_benchmarks_do_not_establish_a_level(repo: TmpRepo) -> None:
    items = [
        {"type": "doc", "path": "docs/RUNS.md", "description": "Notes.", "date": "2026-11-07"},
        {
            "type": "benchmark",
            "path": "docs/RUNS.md",
            "description": "Numbers.",
            "date": "2026-11-07",
        },
    ]
    repo.sources(builtins=[builtin(evidence=items)], plugins=[])
    e = repo.entry("brainos.demo")
    assert e.level is None and all(x.supports is None for x in e.evidence)


def test_r1_a_non_test_file_cannot_be_test_evidence(repo: TmpRepo) -> None:
    repo.sources(
        builtins=[builtin(evidence=[curated_test(path="docs/RUNS.md", anchor=None)])], plugins=[]
    )
    refused(repo, "not a test file")


# ------------------------------------------------------------------- R2 protocol_tested


def test_r2_protocol_test_with_anchor_reaches_protocol_tested(repo: TmpRepo) -> None:
    item = curated_test(anchor="pylsl.StreamOutlet", protocol_reference="Genuine liblsl outlets")
    repo.sources(builtins=[builtin(evidence=[item])], plugins=[])
    e = repo.entry("brainos.demo")
    assert e.level == "protocol_tested" and e.level_number == 2
    assert e.level_basis[1] == "protocol_tested (R2): test_demo.py"
    assert e.level_basis[2].startswith("hardware_verified (R3): not reached")


def test_r2_protocol_claim_without_anchor_is_refused(repo: TmpRepo) -> None:
    item = curated_test(anchor=None, protocol_reference="Genuine liblsl outlets")
    repo.sources(builtins=[builtin(evidence=[item])], plugins=[])
    refused(repo, "a protocol-level test needs an anchor")


def test_r2_protocol_claim_on_a_document_is_refused(repo: TmpRepo) -> None:
    doc = {
        "type": "doc",
        "path": "docs/RUNS.md",
        "description": "Notes.",
        "date": "2026-11-07",
        "protocol_reference": "liblsl",
    }
    repo.sources(builtins=[builtin(evidence=[curated_test(), doc])], plugins=[])
    refused(repo, "protocol_reference is only allowed on test evidence")


def test_r2_certify_protocol_tested_report_supports_protocol_tested(repo: TmpRepo) -> None:
    doc = report(EXAMPLE_REPORT)  # adapter_implementation only
    repo.example_package()
    repo.report(EXAMPLE_REPORT, doc)
    repo.sources(builtins=[], plugins=[example_plugin()])
    e = repo.entry("brainos-example-adapter")
    (ev,) = e.evidence
    assert ev.type == "certify_report" and ev.counted and ev.supports == "software_implemented"
    assert ev.certify is not None and ev.certify.source_matches is True
    assert e.level == "software_implemented" and e.entry_point == "example-mi-eeg"
    assert e.modalities_declared == ["eeg"] and e.module == "brainos_example_adapter"


def test_r2_protocol_tested_report_with_broken_consistency_is_refused(repo: TmpRepo) -> None:
    doc = report(BRAINFLOW_REPORT)
    doc["protocol_reference"]["consistency"][2]["ok"] = False
    repo.report(BRAINFLOW_REPORT, doc)
    refused(repo, "broken consistency rules: reference_names_ecosystem")


# ------------------------------------------------------------------- R3 hardware_verified


def _ev(**over: Any) -> Evidence:
    base: dict[str, Any] = {
        "type": "test",
        "path": "tests/test_x.py",
        "description": "x",
        "date": "2026-11-07",
        "supports": "protocol_tested",
        "counted": True,
    }
    base.update(over)
    return Evidence(**base)


def _attested_report(accepted: bool) -> Evidence:
    info = CertifyInfo(
        level="hardware_tested",
        tool="brainos-certify 0.1.0",
        plugin="p",
        plugin_version="1.0.0",
        entry_point="p",
        device_key=None,
        data_source="p:dev",
        counts={"pass": 29},
        protocol_reference=None,
        attestation_accepted=accepted,
        tree_sha256="0" * 64,
        source_matches=True,
        changed_files=[],
    )
    return _ev(type="certify_report", path="docs/compatibility/p.certify.json", certify=info)


def _comparison() -> Evidence:
    return _ev(
        type="doc",
        path="docs/comparison.md",
        supports=None,
        claim="independent_reference_comparison",
    )


def test_r3_reference_comparison_without_attestation_is_refused(repo: TmpRepo) -> None:
    """An entry claiming hardware_verified without a signed attestation is refused."""
    doc = {
        "type": "doc",
        "path": "docs/RUNS.md",
        "description": "We compared against a reference recording.",
        "date": "2026-11-07",
        "claim": "independent_reference_comparison",
    }
    item = curated_test(anchor="pylsl.StreamOutlet", protocol_reference="Genuine liblsl outlets")
    repo.sources(builtins=[builtin(evidence=[item, doc])], plugins=[])
    refused(repo, "without a counted certify report carrying an accepted, signed operator")
    with pytest.raises(CompatError, match="hardware_verified refused"):
        derive_level([_ev(), _attested_report(accepted=False), _comparison()])


def test_r3_attestation_alone_is_not_hardware_verified() -> None:
    level, _, basis = derive_level([_ev(), _attested_report(accepted=True)])
    assert level == "protocol_tested"
    assert basis[2] == (
        "hardware_verified (R3): not reached: an accepted attestation but no "
        "independent-reference comparison"
    )


def test_r3_needs_protocol_tested_below_it() -> None:
    attested_sw = _attested_report(accepted=True).model_copy(
        update={"supports": "software_implemented"}
    )
    level, _, basis = derive_level(
        [_ev(supports="software_implemented"), attested_sw, _comparison()]
    )
    assert level == "software_implemented"
    assert basis[2] == "hardware_verified (R3): not reached: protocol_tested not reached"


def test_r3_rule_is_reachable_only_with_attestation_and_comparison() -> None:
    """The rule itself, on constructed inputs (no registry entry has such evidence)."""
    level, _, basis = derive_level([_ev(), _attested_report(accepted=True), _comparison()])
    assert level == "hardware_verified"
    assert basis[2] == "hardware_verified (R3): p.certify.json with comparison.md"
    assert basis[3] == "human_validated (R4): never derived by software"


def test_r6_hardware_tested_report_without_accepted_attestation_is_refused(repo: TmpRepo) -> None:
    doc = report(EXAMPLE_REPORT)
    doc["levels"]["achieved"].append("hardware_tested")
    doc["levels"]["highest"] = doc["summary"]["level"] = "hardware_tested"
    doc["levels"]["levels"]["hardware_tested"]["achieved"] = True
    repo.report(EXAMPLE_REPORT, doc)
    refused(repo, "hardware_tested without an accepted operator attestation")


# ------------------------------------------------------------------- R4 human_validated


def test_r4_level_four_claim_is_refused(repo: TmpRepo) -> None:
    doc = {
        "type": "doc",
        "path": "docs/RUNS.md",
        "description": "Approved protocol.",
        "date": "2026-11-07",
        "claim": "approved_human_protocol",
    }
    repo.sources(builtins=[builtin(evidence=[curated_test(), doc])], plugins=[])
    refused(repo, "human_validated is never derived by software")
    with pytest.raises(CompatError, match="R4"):
        derive_level([_ev(), _comparison().model_copy(update={"claim": "approved_human_protocol"})])


def test_r4_certify_report_claiming_human_validation_is_refused(repo: TmpRepo) -> None:
    doc = report(EXAMPLE_REPORT)
    doc["levels"]["levels"]["human_participant_validated"]["achieved"] = True
    repo.report(EXAMPLE_REPORT, doc)
    # refused by the brainos-certify schema (and by certify_problems without it, see below)
    refused(repo, "human_participant_validated")


# ------------------------------------------------------------------- R5 counting


def test_r5_opt_in_test_without_recorded_execution_is_refused(repo: TmpRepo) -> None:
    repo.sources(builtins=[builtin(evidence=[curated_test(runs_in_ci=False)])], plugins=[])
    refused(repo, "counts only with a recorded execution")


def test_r5_opt_in_test_counts_with_its_recorded_execution(repo: TmpRepo) -> None:
    record = {"path": "docs/RUNS.md", "anchor": "passed here on 2026-11-07"}
    repo.sources(
        builtins=[builtin(evidence=[curated_test(runs_in_ci=False, record=record)])], plugins=[]
    )
    (ev,) = repo.entry("brainos.demo").evidence
    assert ev.counted and ev.record == "docs/RUNS.md" and ev.runs_in_ci is False
    record["anchor"] = "passed elsewhere"
    repo.sources(
        builtins=[builtin(evidence=[curated_test(runs_in_ci=False, record=record)])], plugins=[]
    )
    refused(repo, "recorded execution 'passed elsewhere' not found")


def test_r5_report_for_a_different_version_is_not_counted(repo: TmpRepo) -> None:
    doc = report(EXAMPLE_REPORT)
    doc["plugin"]["manifest"]["version"] = "0.0.9"
    doc["plugin"]["identity"]["distribution"]["version"] = "0.0.9"
    repo.example_package()
    repo.report(EXAMPLE_REPORT, doc)
    repo.sources(builtins=[], plugins=[example_plugin()])
    e = repo.entry("brainos-example-adapter")
    (ev,) = e.evidence
    assert not ev.counted and ev.note is not None
    assert ev.note.startswith("Evidence for a different version: the report is for 0.0.9")
    assert e.level is None and e.version == "0.1.0"


def test_r5_report_for_changed_plugin_source_is_not_counted(repo: TmpRepo) -> None:
    repo.example_package()
    repo.report(EXAMPLE_REPORT, report(EXAMPLE_REPORT))
    repo.sources(builtins=[], plugins=[example_plugin()])
    assert repo.entry("brainos-example-adapter").evidence[0].counted
    plugin_py = repo.root / "plugins/example/src/brainos_example_adapter/plugin.py"
    plugin_py.write_text(plugin_py.read_text() + "\n# changed after certification\n")
    (ev,) = repo.entry("brainos-example-adapter").evidence
    assert not ev.counted and ev.certify is not None
    assert ev.certify.source_matches is False and ev.certify.changed_files == ["plugin.py"]
    assert ev.note is not None and "plugin source changed after this run (plugin.py)" in ev.note


def test_r5_report_without_curated_entry_still_listed(repo: TmpRepo) -> None:
    repo.report(BRAINFLOW_REPORT, report(BRAINFLOW_REPORT))
    e = repo.entry("brainos-brainflow")
    assert e.kind == "source_plugin" and not e.in_checkout and e.ecosystem == "brainflow"
    assert e.level == "protocol_tested"  # counted for the version it names (source not here)
    (ev,) = e.evidence
    assert ev.note is not None and ev.note.startswith("Plugin source not in this repository")
    assert any(t.startswith("hardware_tested:") for t in e.not_tested)


# ------------------------------------------------------------------- R6 certify reports


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d.pop("checks"), "does not match the brainos-certify report schema"),
        (lambda d: d["tool"].update(name="other-tool"), "report schema: tool/name"),
        (lambda d: d.update(report_version="9.0"), "report schema: report_version"),
        (
            lambda d: d["summary"].update(level="protocol_tested"),
            "highest level is 'adapter_implementation' but",
        ),
        (lambda d: d["checks"][0].update(status="fail"), "adapter_implementation with failed"),
        (
            lambda d: d["levels"]["levels"]["protocol_tested"].update(achieved=True),
            "levels.protocol_tested.achieved disagrees",
        ),
    ],
    ids=["schema", "tool", "version", "summary-level", "failed-check", "per-level-flag"],
)
def test_r6_inconsistent_certify_report_is_refused(
    repo: TmpRepo, mutate: Callable[[dict[str, Any]], object], match: str
) -> None:
    doc = copy.deepcopy(report(EXAMPLE_REPORT))
    mutate(doc)
    repo.report(EXAMPLE_REPORT, doc)
    refused(repo, match)


def test_r6_consistency_is_checked_without_the_certify_schema() -> None:
    """certify_problems alone (used when brainos-certify is not installed) refuses the same."""
    good = report(EXAMPLE_REPORT)
    assert certify_problems(good) == []
    bad = copy.deepcopy(good)
    bad["tool"]["name"] = "other-tool"
    bad["report_version"] = "9.0"
    bad["levels"]["achieved"].append("human_participant_validated")
    problems = certify_problems(bad)
    assert "not a brainos-certify report (tool.name)" in problems
    assert "unsupported report_version '9.0'" in problems
    assert "claims human_participant_validated, which brainos-certify never sets" in problems
    protocol = report(BRAINFLOW_REPORT)
    assert certify_problems(protocol) == []
    protocol["protocol_reference"] = None
    assert "protocol_tested without a protocol reference statement" in certify_problems(protocol)


# ------------------------------------------------------------------- R7 real-data replay


def test_r7_real_data_needs_a_pinned_manifest(repo: TmpRepo) -> None:
    repo.write("data/manifest.json", json.dumps({"files": [{"sha256": "a" * 64}]}))
    item = curated_test(dataset_manifest="data/manifest.json")
    repo.sources(builtins=[builtin(evidence=[item])], plugins=[])
    e = repo.entry("brainos.demo")
    assert e.real_data_replay and e.evidence[0].real_data
    repo.write("data/manifest.json", json.dumps({"files": [{"name": "x.nwb"}]}))
    refused(repo, "pins no SHA-256 checksums")


# ------------------------------------------------------------------- --check


def test_check_detects_a_stale_registry(repo: TmpRepo, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(repo.root)
    assert main(["--check", "--root", root]) == 1  # never generated
    assert main(["--root", root]) == 0
    assert main(["--check", "--root", root]) == 0
    # evidence changed, registry not regenerated
    repo.sources(
        builtins=[builtin(evidence=[curated_test(description="Changed description.")])], plugins=[]
    )
    assert main(["--check", "--root", root]) == 1
    assert "stale: compat/registry.json" in capsys.readouterr().err
    assert main(["--root", root]) == 0
    # the generated docs section edited by hand
    doc = repo.root / DOC
    doc.write_text(doc.read_text().replace("built-in adapter", "builtin"))
    assert main(["--check", "--root", root]) == 1
    assert f"stale: {DOC}" in capsys.readouterr().err
    assert main(["--root", root]) == 0
    # a hand-edited level in the registry file
    reg = repo.root / REGISTRY
    reg.write_text(reg.read_text().replace('"software_implemented"', '"hardware_verified"', 1))
    assert main(["--check", "--root", root]) == 1


def test_refused_input_exits_2(repo: TmpRepo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.sources(builtins=[builtin(level="hardware_verified")], plugins=[])
    assert main(["--root", str(repo.root)]) == 2
    assert "compatibility registry refused" in capsys.readouterr().err
    assert not (repo.root / REGISTRY).exists()


def test_missing_docs_markers_are_refused(repo: TmpRepo) -> None:
    repo.write(DOC, "# Compatibility\n")
    refused(repo, "registry markers not found")


# ------------------------------------------------------------------- live status


def _entry(**over: Any) -> Any:
    reg = Registry.model_validate_json((REPO_ROOT / REGISTRY).read_bytes())
    entry_id = over.pop("id")
    return next(e for e in reg.entries if e.id == entry_id).model_copy(update=over)


def test_live_builtin_status() -> None:
    lsl = _entry(id="brainos.lsl")
    assert builtin_status(lsl, lsl.version, lambda m: True).state == "installed"
    st = builtin_status(lsl, lsl.version, lambda m: m != "pylsl")
    assert st.state == "unavailable" and st.detail == "Needs pylsl, which is not installed"
    st = builtin_status(lsl, "9.9.9", lambda m: True)
    assert st.state == "different_version" and st.version_matches is False
    assert st.detail.startswith("Evidence for a different version")
    # installation status is what is importable here, not what the registry's checkout had
    gone = builtin_status(lsl, lsl.version, lambda m: m != "brainos.adapters.lsl")
    assert gone.state == "not_installed" and gone.detail == "Not part of this installation"
    t15 = _entry(id="brainos.cursorclick.t15")
    assert t15.module == "brainos.adapters.cursorclick"
    assert builtin_status(t15, t15.version, lambda m: True).state == "installed"
    no_module = _entry(id="brainos.lsl", in_checkout=False, module=None)
    assert builtin_status(no_module, lsl.version, lambda m: True).state == "not_installed"


def test_live_plugin_status() -> None:
    bf = _entry(id="brainos-brainflow")
    assert plugin_status(bf, None).state == "not_checked"
    assert plugin_status(bf, []).state == "not_installed"
    same = InstalledPlugin("brainos-brainflow", bf.version, "compatible", None)
    st = plugin_status(bf, [same])
    assert st.state == "installed" and st.version_matches is True
    other = InstalledPlugin("brainos-brainflow", "0.2.0", "compatible", None)
    st = plugin_status(bf, [other])
    assert st.state == "different_version" and st.installed_version == "0.2.0"
    assert st.detail == (
        f"Evidence for a different version: the evidence is for {bf.version}, 0.2.0 is installed"
    )
    rejected = InstalledPlugin("brainos-brainflow", bf.version, "rejected", "api_version: 2.0")
    st = plugin_status(bf, [rejected])
    assert st.state == "unavailable" and "api_version: 2.0" in st.detail


def test_live_status_never_changes_a_level() -> None:
    reg = Registry.model_validate_json((REPO_ROOT / REGISTRY).read_bytes())
    before = reg.model_dump()
    live = live_status(
        reg, brainos_version="0.0.1", installed_plugins=[], available=lambda m: False
    )
    assert set(live) == {e.id for e in reg.entries}
    assert reg.model_dump() == before


# ------------------------------------------------------------------- REST


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def test_rest_compatibility_serves_the_registry(client: TestClient) -> None:
    body = client.get("/api/v1/compatibility").json()
    assert body["available"] is True and body["error"] is None
    assert body["brainos_version"] == __version__ and body["source"] == "registry.json"
    committed = json.loads((REPO_ROOT / REGISTRY).read_text(encoding="utf-8"))
    assert body["registry"] == committed
    live = body["live"]
    assert set(live) == {e["id"] for e in committed["entries"]}
    assert live["brainos.sim.profile_a"]["state"] == "installed"
    assert live["brainos-brainflow"]["state"] == "not_checked"  # discovery off in tests
    assert body["plugin_discovery"]["discovered_at_ns"] is None


def test_rest_compatibility_after_plugin_discovery(tmp_path: Path) -> None:
    """Real discovery of the installed plugins; a registry whose evidence is for another
    version of one of them reports "evidence for a different version"."""
    reg = json.loads((REPO_ROOT / REGISTRY).read_text(encoding="utf-8"))
    for e in reg["entries"]:
        if e["id"] == "brainos-bci2000":
            e["version"] = "0.0.1"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    with TestClient(create_app(make_settings(tmp_path, compat_registry=path))) as c:
        assert c.post("/api/v1/plugins/discover", json={}).status_code == 200
        body = c.get("/api/v1/compatibility").json()
    live = body["live"]
    assert body["plugin_discovery"]["discovered_at_ns"] is not None
    for pkg in ("brainos-example-adapter", "brainos-brainflow"):
        assert live[pkg]["state"] == "installed" and live[pkg]["version_matches"] is True
    bci = live["brainos-bci2000"]
    assert bci["state"] == "different_version" and bci["installed_version"] == "0.1.0"
    assert bci["detail"].startswith("Evidence for a different version")
    # the level is the evidence's, not the installation's
    assert next(e for e in body["registry"]["entries"] if e["id"] == "brainos-bci2000")["level"]


@pytest.mark.parametrize("content", [None, "{not json", '{"registry_version": "1.0"}'])
def test_rest_compatibility_reports_a_missing_or_invalid_registry(
    tmp_path: Path, content: str | None
) -> None:
    path = tmp_path / "registry.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with TestClient(create_app(make_settings(tmp_path, compat_registry=path))) as c:
        r = c.get("/api/v1/compatibility")
        diag = c.get("/api/v1/diagnostics").json()
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False and body["registry"] is None and body["live"] == {}
    assert body["error"].startswith("compatibility registry unavailable (registry.json)")
    assert any(e["kind"] == "compatibility_registry" for e in diag["recent_errors"])
