"""PyTorch: TorchScript and safetensors state_dicts (skipped only when torch is absent)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from dec_helpers import RNG, WIDTH, load_error, manifest, run_host

from concord_decoder_sdk.formats import write_bundle

# ----------------------------------------------------------------------------- PyTorch


def _torch() -> Any:
    return pytest.importorskip(
        "torch", reason="torch is not installed (optional extra concord-decoder-sdk[torch])"
    )


def test_torchscript_recurrent_model(tmp_path: Path) -> None:
    torch = _torch()
    from concord_decoder_sdk.architectures import GRUReadout

    torch.manual_seed(0)
    net = GRUReadout(WIDTH, 5, 2).eval()
    scripted = torch.jit.trace(net, (torch.zeros(1, WIDTH), torch.zeros(1, 1, 5)))
    scripted.save(str(tmp_path / "gru.pt"))
    io: Mapping[str, Any] = {"state_shape": [1, 1, 5]}
    path = write_bundle(
        tmp_path / "m", manifest("ts-gru", "torchscript"), tmp_path / "gru.pt", "torchscript", io
    )
    x = RNG.poisson(2.0, (12, WIDTH)).astype(np.float64)
    h = torch.zeros(1, 1, 5)
    ref = []
    with torch.no_grad():
        for row in x:
            y, h = net(torch.as_tensor(row[None, :], dtype=torch.float32), h)
            ref.append(y.numpy()[0])
    np.testing.assert_allclose(
        run_host(path, x), np.array(ref, dtype=np.float64), rtol=1e-6, atol=1e-6
    )


def test_safetensors_state_dict_into_builtin_architecture(tmp_path: Path) -> None:
    torch = _torch()
    st = pytest.importorskip("safetensors.torch", reason="safetensors (torch extra)")
    torch.manual_seed(1)
    lin = torch.nn.Linear(WIDTH, 2)
    st.save_file(lin.state_dict(), str(tmp_path / "lin.safetensors"))
    path = write_bundle(
        tmp_path / "m",
        manifest("st-lin", "torch-linear"),
        tmp_path / "lin.safetensors",
        "safetensors",
        {"architecture": "linear"},
    )
    x = RNG.poisson(2.0, (6, WIDTH)).astype(np.float64)
    with torch.no_grad():
        ref = lin(torch.as_tensor(x, dtype=torch.float32)).numpy()
    np.testing.assert_allclose(run_host(path, x), ref, rtol=1e-6, atol=1e-6)
    # a state_dict that does not fit the declared architecture is refused (strict loading)
    wrong = torch.nn.Linear(WIDTH + 1, 2)
    st.save_file(wrong.state_dict(), str(tmp_path / "wrong.safetensors"))
    bad = write_bundle(
        tmp_path / "m2",
        manifest("st-wrong", "torch-linear"),
        tmp_path / "wrong.safetensors",
        "safetensors",
        {"architecture": "linear"},
    )
    assert "do not match the declared architecture" in load_error(bad).message
    unknown = write_bundle(
        tmp_path / "m3",
        manifest("st-arch", "torch-linear"),
        tmp_path / "lin.safetensors",
        "safetensors",
        {"architecture": "transformer"},
    )
    assert "unknown architecture" in load_error(unknown).message


def test_write_bundle_refuses_invalid_manifests(tmp_path: Path) -> None:
    src = tmp_path / "f.onnx"
    src.write_bytes(b"x")
    bad = dataclasses.replace(manifest("ok", "onnx"), modalities=frozenset())
    with pytest.raises(ValueError, match="modalities"):
        write_bundle(tmp_path / "m", bad, src, "onnx")
    assert not list((tmp_path / "m").glob("*"))
