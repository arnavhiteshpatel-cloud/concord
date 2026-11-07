"""Cursor + click reader/catalog error paths (synthetic .mat files; only for cases the real
published files cannot exercise: malformed or unverified files)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

scipy_io = pytest.importorskip("scipy.io")

from brainos.adapters.cursorclick.catalog import CursorClickCatalog  # noqa: E402
from brainos.adapters.cursorclick.reader import T15FormatError, load  # noqa: E402
from brainos.adapters.cursorclick.source import T15CursorClickSource  # noqa: E402
from brainos.adapters.simulated import OperatorIntentSource  # noqa: E402
from brainos.runtime import DeviceRegistry  # noqa: E402
from brainos.runtime.registry import DeviceNotFoundError  # noqa: E402

NAME = "t15_day00468_block03_grid_evaluation_task.mat"


def fields(n: int = 200, ch: int = 4) -> dict[str, Any]:
    rng = np.random.default_rng(0)
    return {
        "timestamp_sec": np.arange(n) * 0.01,
        "threshold_crossings": rng.integers(0, 3, (n, ch)).astype(np.int16),
        "spike_band_power": rng.uniform(10, 100, (n, ch)).astype(np.float32),
        "assist_amount": np.zeros(n),
        "cursor_position": np.zeros((n, 2)),
        "target_position": np.full((n, 2), 0.1),
        "trial_idx": np.zeros(n),
        "cursor_decoder_output": np.zeros((n, 2)),
        "click_decoder_output": np.zeros(n),
        "click_assist": np.zeros(n, dtype=bool),
        "trial_start_bin": np.array([0, 100]),
        "cursor_radius": 0.012,
        "grid_num_rows": 14.0,
        "grid_total_height": 0.92,
        "array_label_by_electrode": np.array(["v6v"] * ch),
    }


def write(path: Path, data: dict[str, Any]) -> Path:
    scipy_io.savemat(str(path), data)
    return path


def test_well_formed_synthetic_file_loads_but_is_labelled_unverified(tmp_path: Path) -> None:
    p = write(tmp_path / NAME, fields())
    b = load(p)
    assert b.n_bins == 200 and b.channel_count == 4 and b.has_click
    src = T15CursorClickSource(p)
    assert not src.verification.verified
    assert src.origin == f"file:{NAME}"
    assert "unverified local file" in src.descriptor().description


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"threshold_crossings": None}, "missing fields"),
        ({"spike_band_power": np.ones((200, 3), dtype=np.float32)}, "differ"),
        ({"timestamp_sec": np.arange(200) * 0.02}, "contiguous 10 ms"),
        ({"cursor_position": np.zeros((199, 2))}, "bins"),
        ({"spike_band_power": np.full((200, 4), np.nan, dtype=np.float32)}, "non-finite"),
        ({"array_label_by_electrode": np.array(["v6v"] * 3)}, "array labels"),
    ],
)
def test_malformed_file_refused(tmp_path: Path, change: dict[str, Any], match: str) -> None:
    data = fields()
    for k, v in change.items():
        if v is None:
            data.pop(k)
        else:
            data[k] = v
    with pytest.raises(T15FormatError, match=match):
        load(write(tmp_path / NAME, data))


def test_unexpected_file_name_refused(tmp_path: Path) -> None:
    with pytest.raises(T15FormatError, match="not a cursor"):
        load(write(tmp_path / "session.mat", fields()))


def test_catalog_lists_good_files_and_reports_bad_ones(tmp_path: Path) -> None:
    ds = tmp_path / "datasets"
    ds.mkdir()
    write(ds / NAME, fields())
    bad = fields()
    bad.pop("spike_band_power")
    write(ds / "t15_day00468_block04_grid_evaluation_task.mat", bad)
    cat = CursorClickCatalog(ds)
    ids = [d.device_id for d in cat.list()]
    assert ids == ["t15:day00468-block03-grid-evaluation"]
    assert [p.file for p in cat.problems] == ["t15_day00468_block04_grid_evaluation_task.mat"]
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "recordings", datasets_dir=ds)
    assert "t15:day00468-block03-grid-evaluation" in [d.device_id for d in reg.list()]
    assert reg.describe("t15:day00468-block03-grid-evaluation").modality == "intracortical"
    with pytest.raises(DeviceNotFoundError):
        reg.describe("t15:day00468-block99-grid-evaluation")
    with pytest.raises(DeviceNotFoundError):
        reg.create("t15:day00468-block99-grid-evaluation")
