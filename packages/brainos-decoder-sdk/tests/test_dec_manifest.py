"""Manifest validation (valid + malformed), JSON round trip, output validation."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import numpy as np
import pytest
from bos_test_decoders import BASE
from dec_helpers import DECODERS_DIR  # noqa: F401  (puts the test decoders on sys.path)

from brainos_decoder_sdk import (
    Artifact,
    Confidence,
    InputSpec,
    Modality,
    OutputKind,
    OutputSpec,
    ParticipantCompat,
    Preprocessing,
)
from brainos_decoder_sdk import manifest as mf


def codes(m: object) -> set[str]:
    return {p.code for p in mf.validate_manifest(m) if p.severity == "error"}


def test_valid_manifest_has_no_errors_and_round_trips() -> None:
    assert codes(BASE) == set()
    d = mf.manifest_to_dict(BASE)
    assert d["schema"] == "brainos.decoder-manifest/1"
    back = mf.manifest_from_dict(json.loads(json.dumps(d)))
    assert back == BASE


I0 = BASE.inputs[0]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"model_id": "has space"}, "manifest.model_id"),
        ({"model_id": ""}, "manifest.model_id"),
        ({"version": "1.0"}, "manifest.version"),
        ({"api_version": "2.0"}, "manifest.api_version"),
        ({"api_version": "1.9"}, "manifest.api_version"),
        ({"api_version": "one"}, "manifest.api_version"),
        ({"family": "Bad Family"}, "manifest.family"),
        ({"description": ""}, "manifest.description"),
        ({"author": 3}, "manifest.author"),
        ({"modalities": frozenset()}, "manifest.modalities"),
        ({"modalities": frozenset({"eeg"})}, "manifest.modalities"),
        ({"inputs": ()}, "manifest.inputs"),
        ({"inputs": (dataclasses.replace(I0, event_type="recording.frame"),)}, "input.event_type"),
        ({"inputs": (dataclasses.replace(I0, feature="log_band_power"),)}, "input.feature"),
        ({"inputs": (dataclasses.replace(I0, feature="Bad Name"),)}, "input.feature"),
        ({"inputs": (dataclasses.replace(I0, bin_ms=0.0),)}, "input.bin_ms"),
        ({"inputs": (dataclasses.replace(I0, bin_ms=float("nan")),)}, "input.bin_ms"),
        ({"inputs": (dataclasses.replace(I0, channel_count=0),)}, "input.channel_count"),
        ({"inputs": (dataclasses.replace(I0, channel_count=True),)}, "input.channel_count"),
        ({"inputs": (dataclasses.replace(I0, channel_labels=("a", "b")),)}, "input.labels"),
        ({"inputs": (dataclasses.replace(I0, unit=""),)}, "input.unit"),
        ({"inputs": (dataclasses.replace(I0, band_hz=(30.0, 8.0)),)}, "input.band_hz"),
        ({"inputs": (I0, I0)}, "manifest.inputs"),  # duplicate feature stream
        (
            {
                "inputs": (
                    I0,
                    InputSpec("features.vector", "log_band_power", 50.0, 4, None, "log10(uV^2)"),
                )
            },
            "manifest.inputs",  # different bin sizes cannot be joined
        ),
        ({"output": dataclasses.replace(BASE.output, dims=())}, "output.dims"),
        ({"output": dataclasses.replace(BASE.output, dims=("vx", "vx"))}, "output.dims"),
        ({"output": dataclasses.replace(BASE.output, dims=("v x",))}, "output.dims"),
        ({"output": dataclasses.replace(BASE.output, scale=(1.0,))}, "output.scale"),
        ({"output": dataclasses.replace(BASE.output, scale=(1.0, -1.0))}, "output.scale"),
        (
            {
                "output": OutputSpec(
                    OutputKind.CLASSES, "class_posterior", ("one",), "probability", "c"
                )
            },
            "output.classes",
        ),
        (
            {"output": OutputSpec(OutputKind.EVENT, "click_probability", ("click",), "count", "c")},
            "output.unit",
        ),
        ({"confidence": Confidence.POSTERIOR}, "manifest.confidence"),
        ({"preprocessing": Preprocessing("x", {"k": float("inf")})}, "preprocessing.params"),
        ({"compatibility": ParticipantCompat(sessions=("",))}, "compatibility.sessions"),
        ({"artifact": Artifact("exe", "m.bin", "0" * 64)}, "artifact.format"),
        ({"artifact": Artifact("onnx", "../m.onnx", "0" * 64)}, "artifact.file"),
        ({"artifact": Artifact("onnx", "m.onnx", "abc")}, "artifact.sha256"),
    ],
)
def test_malformed_manifest_is_rejected(change: dict[str, Any], code: str) -> None:
    assert code in codes(dataclasses.replace(BASE, **change))


def test_warnings_are_not_errors() -> None:
    m = dataclasses.replace(
        BASE,
        inputs=(dataclasses.replace(I0, channel_labels=("a", "a", "b", "c")),),
        compatibility=ParticipantCompat(source_identity=None),
        artifact=Artifact("pickle", "m.pkl", "0" * 64),
    )
    probs = mf.validate_manifest(m)
    assert not mf.has_errors(probs)
    assert {p.code for p in probs} >= {
        "input.labels.duplicate",
        "compatibility.source_unknown",
        "artifact.unsafe_format",
    }


def test_not_a_manifest() -> None:
    assert codes({"model_id": "x"}) == {"manifest.type"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("inputs"),
        lambda d: d.update(modalities=["telepathy"]),
        lambda d: d.update(modalities="eeg"),
        lambda d: d["output"].update(kind="vibes"),
        lambda d: d.update(confidence="certain"),
        lambda d: d.update(schema="brainos.decoder-manifest/9"),
        lambda d: d.update(output=[]),
        lambda d: d["inputs"][0].update(bin_ms="fast"),
        lambda d: d.update(artifact="model.onnx"),
    ],
)
def test_structurally_broken_dicts_raise(mutate: Any) -> None:
    d = mf.manifest_to_dict(BASE)
    mutate(d)
    with pytest.raises(mf.ManifestError):
        mf.manifest_from_dict(d)


def test_api_versions() -> None:
    assert mf.api_compatible("1.0")[0]
    assert not mf.api_compatible("1.1")[0]  # newer minor than this host
    assert "major versions differ" in mf.api_compatible("0.9")[1]


# ----------------------------------------------------------------------------- outputs


def test_output_validator_continuous_and_confidence() -> None:
    v = mf.OutputValidator(BASE)
    assert v.check(np.array([0.1, -3.0])) == []
    assert {p.code for p in v.check(np.array([0.1]))} == {"output.values.shape"}
    assert {p.code for p in v.check(np.array([np.inf, 0.0]))} == {"output.values.finite"}
    assert {p.code for p in v.check("nope")} == {"output.values.type"}
    assert {p.code for p in v.check(np.array([0.0, 0.0]), np.ones(2))} == {"output.confidence"}
    var = mf.OutputValidator(dataclasses.replace(BASE, confidence=Confidence.VARIANCE))
    assert var.check(np.zeros(2), np.array([0.1, 0.2])) == []
    assert {p.code for p in var.check(np.zeros(2))} == {"output.confidence.missing"}
    assert {p.code for p in var.check(np.zeros(2), np.array([-1.0, 0.2]))} == {
        "output.confidence.negative"
    }
    cov = mf.OutputValidator(dataclasses.replace(BASE, confidence=Confidence.COVARIANCE))
    assert cov.check(np.zeros(2), np.array([[1.0, 0.2], [0.2, 2.0]])) == []
    assert {p.code for p in cov.check(np.zeros(2), np.array([[1.0, 0.5], [0.2, 2.0]]))} == {
        "output.confidence.symmetric"
    }
    assert {p.code for p in cov.check(np.zeros(2), np.ones(2))} == {"output.confidence.shape"}


def test_output_validator_probabilities() -> None:
    cls = mf.OutputValidator(
        dataclasses.replace(
            BASE,
            output=OutputSpec(
                OutputKind.CLASSES, "class_posterior", ("a", "b", "c"), "probability", "s"
            ),
            confidence=Confidence.POSTERIOR,
        )
    )
    assert cls.check(np.array([0.2, 0.3, 0.5])) == []
    assert {p.code for p in cls.check(np.array([0.2, 0.3, 0.6]))} == {"output.values.sum"}
    assert "output.values.probability" in {p.code for p in cls.check(np.array([1.5, -0.5, 0.0]))}
    ev = mf.OutputValidator(
        dataclasses.replace(
            BASE,
            output=OutputSpec(
                OutputKind.EVENT, "click_probability", ("click",), "probability", "s"
            ),
            confidence=Confidence.POSTERIOR,
        )
    )
    assert ev.check(np.array([0.93])) == []
    assert {p.code for p in ev.check(np.array([1.2]))} == {"output.values.probability"}
    row, probs = ev.check_batch(np.array([[0.1], [0.4], [2.0]]), None)
    assert row == 2 and probs


def test_modalities_enum_matches_contract_values() -> None:
    assert {m.value for m in Modality} == {
        "eeg",
        "meg",
        "emg",
        "ecog",
        "seeg",
        "intracortical",
        "other",
    }
