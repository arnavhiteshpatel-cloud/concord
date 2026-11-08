"""How a validation level is derived from evidence (pure; no I/O).

The levels are those of docs/VALIDATION_LEVELS.md, exactly. A level is never typed in: each
evidence item is classified by what it supports (:func:`support_of_test`,
:func:`certify_support`), and :func:`derive_level` takes the highest level whose rule holds.
Levels never auto-promote: each rule requires the one below it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from concord.compat.model import Evidence, Level, LevelDefinition, SourceEvidence

Support = Literal["software_implemented", "protocol_tested"]


class CompatError(ValueError):
    """Refused input: the registry is not written."""


LEVEL_DEFINITIONS: tuple[LevelDefinition, ...] = (
    LevelDefinition(
        id="software_implemented",
        number=1,
        name="Software-implemented",
        meaning="Code exists, is type-checked, and passes unit tests on inputs we constructed.",
    ),
    LevelDefinition(
        id="protocol_tested",
        number=2,
        name="Protocol-tested",
        meaning="Exercised over the real protocol stack by software publishers, in a separate "
        "process where relevant; where an official reference implementation exists, it was run "
        "against our output.",
    ),
    LevelDefinition(
        id="hardware_verified",
        number=3,
        name="Hardware-verified",
        meaning="Run against real acquisition hardware through its real producer software, with "
        "integrity and timing checked against an independent reference.",
    ),
    LevelDefinition(
        id="human_validated",
        number=4,
        name="Human-participant validated",
        meaning="Run with a participant, in a closed loop, under an approved research protocol, "
        "with performance measured by pre-registered metrics.",
    ),
)
LEVEL_NUMBER: dict[Level, int] = {d.id: d.number for d in LEVEL_DEFINITIONS}

RULES: tuple[str, ...] = (
    "R1 software_implemented: at least one counted test file, or a counted concord-certify "
    "report that achieved adapter_implementation.",
    "R2 protocol_tested: R1, and a counted concord-certify report that achieved protocol_tested "
    "(every consistency rule holds), or a counted test that names the real protocol stack or "
    "official reference implementation it runs against (protocol_reference) and contains the "
    "anchor text tying it to that stack.",
    "R3 hardware_verified: R2, and a counted certify report whose hardware_tested level rests on "
    "an accepted (signature-verified) operator attestation, and a document of a comparison "
    "against an independent reference. An attestation alone is not level 3; a comparison "
    "document without an accepted attestation is refused.",
    "R4 human_validated: never derived by software. It requires an approved human-research "
    "protocol run by qualified investigators; any evidence claiming it is refused.",
    "R5 counting: a test that does not run in CI counts only with a recorded execution (a "
    "document containing the given anchor). A certify report counts only if its plugin version "
    "and plugin source files (tree_sha256) equal this checkout's; otherwise it is listed and "
    "not counted. Benchmarks and documents are context; they do not establish a level.",
    "R6 refused (nothing is written): a missing evidence path or anchor, a typed-in level or any "
    "unknown field, a malformed or internally inconsistent certify report, a certify report "
    "claiming human_participant_validated, hardware_tested without an accepted attestation, "
    "and the claims refused by R3 and R4.",
    "R7 real-data replay (beside level 2, not a level): a counted test that reads recordings "
    "pinned by SHA-256 in a dataset manifest.",
)

CERTIFY_LEVELS = ("adapter_implementation", "protocol_tested", "hardware_tested")


# ------------------------------------------------------------------------- per item


def support_of_test(item: SourceEvidence) -> Support:
    """R1 / R2 for a curated test (its files and anchors are verified by the builder)."""
    return "protocol_tested" if item.protocol_reference else "software_implemented"


def check_source_item(item: SourceEvidence, where: str) -> None:
    """Field combinations that are refused regardless of file contents."""
    if item.type != "test":
        for name in ("protocol_reference", "runs_in_ci", "record", "dataset_manifest"):
            if getattr(item, name) is not None:
                raise CompatError(f"{where}: {name} is only allowed on test evidence")
    if item.type != "doc" and item.claim is not None:
        raise CompatError(f"{where}: claim is only allowed on doc evidence")
    if item.type == "test":
        if item.runs_in_ci is None:
            raise CompatError(f"{where}: a test must state runs_in_ci")
        if item.protocol_reference and not item.anchor:
            raise CompatError(
                f"{where}: a protocol-level test needs an anchor: text in the test that ties it "
                "to the named protocol stack"
            )
        if item.runs_in_ci is False and item.record is None:
            raise CompatError(
                f"{where}: a test that does not run in CI counts only with a recorded execution "
                "(record: a document and an anchor in it)"
            )
        if item.runs_in_ci is True and item.record is not None:
            raise CompatError(f"{where}: record is only for tests that do not run in CI")
    if item.claim == "approved_human_protocol":
        raise CompatError(
            f"{where}: human_validated is never derived by software (R4): a registry entry "
            "cannot claim an approved human-research protocol"
        )


def certify_achieved(report: Mapping[str, Any]) -> list[str]:
    levels = report.get("levels")
    achieved = levels.get("achieved") if isinstance(levels, Mapping) else None
    if not isinstance(achieved, list):
        return []
    return [str(x) for x in achieved]


def certify_support(achieved: Sequence[str]) -> Support | None:
    """R1 / R2: what a certification report supports by itself."""
    if "protocol_tested" in achieved:
        return "protocol_tested"
    if "adapter_implementation" in achieved:
        return "software_implemented"
    return None


def certify_problems(report: Mapping[str, Any]) -> list[str]:
    """Internal consistency of a concord-certify report (R6). Empty: consistent."""
    out: list[str] = []
    tool = report.get("tool")
    if not isinstance(tool, Mapping) or tool.get("name") != "concord-certify":
        out.append("not a concord-certify report (tool.name)")
    if report.get("report_version") != "1.0":
        out.append(f"unsupported report_version {report.get('report_version')!r}")
    levels = report.get("levels")
    summary = report.get("summary")
    if not isinstance(levels, Mapping) or not isinstance(summary, Mapping):
        return [*out, "levels / summary missing"]
    achieved = certify_achieved(report)
    per = levels.get("levels")
    if not isinstance(per, Mapping):
        return [*out, "levels.levels missing"]
    if "human_participant_validated" in achieved or (
        isinstance(per.get("human_participant_validated"), Mapping)
        and per["human_participant_validated"].get("achieved") is not False
    ):
        out.append("claims human_participant_validated, which concord-certify never sets")
    for name in achieved:
        if name not in CERTIFY_LEVELS:
            out.append(f"unknown certification level {name!r}")
    for name in CERTIFY_LEVELS:
        entry = per.get(name)
        flag = entry.get("achieved") if isinstance(entry, Mapping) else None
        if flag is not (name in achieved):
            out.append(f"levels.{name}.achieved disagrees with levels.achieved")
    highest = levels.get("highest")
    want = next((n for n in reversed(CERTIFY_LEVELS) if n in achieved), None)
    if highest != want or summary.get("level") != want:
        out.append(f"highest level is {want!r} but the report states {highest!r}")
    checks = report.get("checks")
    failed = [
        str(c.get("id"))
        for c in checks or []
        if isinstance(c, Mapping) and c.get("status") == "fail"
    ]
    if "adapter_implementation" in achieved:
        if failed:
            out.append(f"adapter_implementation with failed checks: {', '.join(failed)}")
        if summary.get("exit_code") != 0:
            out.append("adapter_implementation with a non-zero exit code")
    if "protocol_tested" in achieved:
        if "adapter_implementation" not in achieved:
            out.append("protocol_tested without adapter_implementation")
        ref = report.get("protocol_reference")
        statement = ref.get("statement") if isinstance(ref, Mapping) else None
        if not isinstance(statement, str) or not statement.strip():
            out.append("protocol_tested without a protocol reference statement")
        rules = ref.get("consistency") if isinstance(ref, Mapping) else None
        broken = [
            str(r.get("rule"))
            for r in rules or []
            if isinstance(r, Mapping) and r.get("ok") is False
        ]
        if broken:
            out.append(f"protocol_tested with broken consistency rules: {', '.join(broken)}")
    if "hardware_tested" in achieved:
        att = report.get("attestation")
        if not isinstance(att, Mapping) or att.get("accepted") is not True:
            out.append("hardware_tested without an accepted operator attestation")
        if "adapter_implementation" not in achieved:
            out.append("hardware_tested without adapter_implementation")
    return out


# ------------------------------------------------------------------------- per entry


def _names(items: Sequence[Evidence]) -> str:
    return ", ".join(e.path.rsplit("/", 1)[-1] for e in items)


def derive_level(evidence: Sequence[Evidence]) -> tuple[Level | None, bool, list[str]]:
    """The highest level whose rule holds, whether real-data replay applies, and the trace.

    Raises :class:`CompatError` for over-claims (R3 / R4)."""
    if any(e.claim == "approved_human_protocol" for e in evidence):
        raise CompatError("human_validated is never derived by software (R4)")
    counted = [e for e in evidence if e.counted]
    sw = [e for e in counted if e.supports is not None]
    proto = [e for e in counted if e.supports == "protocol_tested"]
    attested = [e for e in counted if e.certify is not None and e.certify.attestation_accepted]
    comparison = [e for e in counted if e.claim == "independent_reference_comparison"]
    if comparison and not attested:
        raise CompatError(
            "an independent-reference comparison is claimed without a counted certify report "
            "carrying an accepted, signed operator attestation (R3): hardware_verified refused"
        )
    level: Level | None = None
    basis: list[str] = []
    if sw:
        level = "software_implemented"
        basis.append(f"software_implemented (R1): {_names(sw)}")
    else:
        basis.append("software_implemented (R1): not reached: no counted test or certify report")
    if level is not None and proto:
        level = "protocol_tested"
        basis.append(f"protocol_tested (R2): {_names(proto)}")
    elif level is not None:
        basis.append("protocol_tested (R2): not reached: no counted protocol-level evidence")
    else:
        basis.append("protocol_tested (R2): not reached: software_implemented not reached")
    if level == "protocol_tested" and attested and comparison:
        level = "hardware_verified"
        basis.append(f"hardware_verified (R3): {_names(attested)} with {_names(comparison)}")
    elif level == "protocol_tested":
        why = (
            "an accepted attestation but no independent-reference comparison"
            if attested
            else "no signed operator attestation and no independent-reference comparison"
        )
        basis.append(f"hardware_verified (R3): not reached: {why}")
    else:
        basis.append("hardware_verified (R3): not reached: protocol_tested not reached")
    basis.append("human_validated (R4): never derived by software")
    real = any(e.real_data for e in counted)
    return level, real, basis


def level_number(level: Level | None) -> int | None:
    return LEVEL_NUMBER[level] if level is not None else None
