"""ONNX loader: real models built with onnx.helper, loaded through a real decoder host."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from dec_helpers import RNG, WIDTH, load_error, manifest, run_host

from concord_decoder_sdk import ipc
from concord_decoder_sdk.formats import sha256_file, write_bundle

# ----------------------------------------------------------------------------- ONNX

onnx = pytest.importorskip("onnx", reason="onnx (dev extra) builds the ONNX test models")
pytest.importorskip("onnxruntime", reason="onnxruntime is the ONNX loader (onnx extra)")
from onnx import TensorProto, helper, numpy_helper  # noqa: E402


def _save_onnx(graph: Any, path: Path) -> Path:
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return path


def linear_onnx(path: Path, w: np.ndarray, b: np.ndarray) -> Path:
    g = helper.make_graph(
        [
            helper.make_node("MatMul", ["features", "W"], ["xw"]),
            helper.make_node("Add", ["xw", "b"], ["values"]),
        ],
        "linear",
        [helper.make_tensor_value_info("features", TensorProto.DOUBLE, ["batch", WIDTH])],
        [helper.make_tensor_value_info("values", TensorProto.DOUBLE, ["batch", 2])],
        [numpy_helper.from_array(w, "W"), numpy_helper.from_array(b, "b")],
    )
    return _save_onnx(g, path)


def recurrent_onnx(path: Path, wx: np.ndarray, wh: np.ndarray, wy: np.ndarray) -> Path:
    """h' = tanh(x Wx + h Wh); y = h' Wy — a small linear-recurrent (temporal) model."""
    hidden = wh.shape[0]
    g = helper.make_graph(
        [
            helper.make_node("MatMul", ["features", "Wx"], ["a"]),
            helper.make_node("MatMul", ["h_in", "Wh"], ["c"]),
            helper.make_node("Add", ["a", "c"], ["pre"]),
            helper.make_node("Tanh", ["pre"], ["h_out"]),
            helper.make_node("MatMul", ["h_out", "Wy"], ["values"]),
        ],
        "rnn",
        [
            helper.make_tensor_value_info("features", TensorProto.DOUBLE, [1, WIDTH]),
            helper.make_tensor_value_info("h_in", TensorProto.DOUBLE, [1, hidden]),
        ],
        [
            helper.make_tensor_value_info("values", TensorProto.DOUBLE, [1, 2]),
            helper.make_tensor_value_info("h_out", TensorProto.DOUBLE, [1, hidden]),
        ],
        [numpy_helper.from_array(a, n) for a, n in ((wx, "Wx"), (wh, "Wh"), (wy, "Wy"))],
    )
    return _save_onnx(g, path)


LIN_IO: dict[str, Any] = {
    "input": {"name": "features", "shape": ["batch", WIDTH]},
    "output": {"name": "values", "shape": ["batch", 2]},
}


def test_onnx_linear_matches_numpy(tmp_path: Path) -> None:
    w, b = RNG.standard_normal((WIDTH, 2)), RNG.standard_normal(2)
    src = linear_onnx(tmp_path / "src.onnx", w, b)
    path = write_bundle(tmp_path / "models", manifest("onnx-lin", "onnx"), src, "onnx", LIN_IO)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["artifact"]["sha256"] == sha256_file(tmp_path / "models" / "onnx-lin.onnx")
    x = RNG.poisson(3.0, (25, WIDTH)).astype(np.float64)
    np.testing.assert_allclose(run_host(path, x), x @ w + b, rtol=1e-12, atol=1e-12)


def test_onnx_recurrent_state_is_carried_and_reset(tmp_path: Path) -> None:
    hidden = 3
    wx, wh, wy = (
        RNG.standard_normal(s) * 0.5 for s in ((WIDTH, hidden), (hidden, hidden), (hidden, 2))
    )
    src = recurrent_onnx(tmp_path / "src.onnx", wx, wh, wy)
    io = {
        "input": {"name": "features", "shape": [1, WIDTH]},
        "output": {"name": "values", "shape": [1, 2]},
        "state": [{"input": "h_in", "output": "h_out", "shape": [1, hidden]}],
    }
    path = write_bundle(tmp_path / "m", manifest("onnx-rnn", "onnx"), src, "onnx", io)
    x = RNG.poisson(2.0, (30, WIDTH)).astype(np.float64)
    h = np.zeros(hidden)
    ref = []
    for row in x:
        h = np.tanh(row @ wx + h @ wh)
        ref.append(h @ wy)
    np.testing.assert_allclose(run_host(path, x), np.array(ref), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize(
    ("io", "message"),
    [
        (
            {**LIN_IO, "input": {"name": "x", "shape": ["batch", WIDTH]}},
            "ONNX inputs are ['features']",
        ),
        ({**LIN_IO, "output": {"name": "values", "shape": ["batch", 3]}}, "is not [1, 2]"),
        (
            {**LIN_IO, "input": {"name": "features", "shape": ["batch", 5]}},
            "does not take one bin of 4",
        ),
        ({"output": LIN_IO["output"]}, "must declare a tensor name"),
    ],
)
def test_onnx_declared_io_is_checked(tmp_path: Path, io: dict[str, Any], message: str) -> None:
    src = linear_onnx(tmp_path / "src.onnx", RNG.standard_normal((WIDTH, 2)), np.zeros(2))
    path = write_bundle(tmp_path / "m", manifest("onnx-io", "onnx"), src, "onnx", io)
    err = load_error(path)
    assert err.type == ipc.MODEL_LOAD_ERROR and message in err.message


def test_onnx_model_with_wrong_feature_width_for_the_manifest(tmp_path: Path) -> None:
    src = linear_onnx(tmp_path / "src.onnx", RNG.standard_normal((WIDTH, 2)), np.zeros(2))
    m = manifest("onnx-width", "onnx")
    m = dataclasses.replace(m, inputs=(dataclasses.replace(m.inputs[0], channel_count=6),))
    io = {**LIN_IO, "input": {"name": "features", "shape": ["batch", 6]}}
    err = load_error(write_bundle(tmp_path / "m", m, src, "onnx", io))
    assert "has shape ['batch', 4]" in err.message


def test_tampered_artifact_is_refused(tmp_path: Path) -> None:
    src = linear_onnx(tmp_path / "src.onnx", RNG.standard_normal((WIDTH, 2)), np.zeros(2))
    path = write_bundle(tmp_path / "m", manifest("onnx-t", "onnx"), src, "onnx", LIN_IO)
    with (tmp_path / "m" / "onnx-t.onnx").open("ab") as fh:
        fh.write(b"\0")
    err = load_error(path)
    assert "changed since its manifest was written" in err.message


def test_not_an_onnx_file(tmp_path: Path) -> None:
    src = tmp_path / "junk.onnx"
    src.write_bytes(b"this is not protobuf" * 10)
    err = load_error(write_bundle(tmp_path / "m", manifest("junk", "onnx"), src, "onnx", LIN_IO))
    assert err.type == ipc.MODEL_LOAD_ERROR and "onnxruntime cannot load" in err.message
