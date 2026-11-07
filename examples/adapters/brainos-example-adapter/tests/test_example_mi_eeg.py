"""Tests a plugin author would write: run the plugin exactly as BrainOS does (in a separate
host process, with BrainOS's validation) using only the adapter SDK.

    pip install -e .        # registers the entry point
    pytest tests/
"""

from __future__ import annotations

import numpy as np
from brainos_adapter_sdk import Chunk, MarkerChunk
from brainos_adapter_sdk.client import SyncHostClient

from brainos_example_adapter.generator import GeneratorConfig, MotorImageryGenerator


def test_manifest_is_compatible() -> None:
    with SyncHostClient("example-mi-eeg") as host:
        result = host.manifest()
        assert result["compatible"], result["problems"]
        assert result["problems"] == []


def test_streams_and_data_pass_validation() -> None:
    with SyncHostClient("example-mi-eeg") as host:
        devices = host.discover()["devices"]
        assert [d["device_key"] for d in devices] == ["mi-eeg"]
        info = host.open("mi-eeg", {"seed": 5})["info"]
        assert [s["stream_id"] for s in info["streams"]] == ["eeg", "cue", "markers"]
        eeg: list[Chunk] = []
        markers: list[MarkerChunk] = []
        while sum(c.data.shape[0] for c in eeg) < 500:  # 2 s of data; the host validates it
            for c in host.read(0.2):
                if isinstance(c, MarkerChunk):
                    markers.append(c)
                elif c.stream_id == "eeg":
                    eeg.append(c)
        data = np.concatenate([c.data for c in eeg])
        assert data.dtype == np.float32 and data.shape[1] == 8
        # same seed -> same samples, independent of timing
        gen = MotorImageryGenerator(GeneratorConfig(seed=5))
        expected = np.concatenate([gen.next_block().eeg for _ in range(len(data) // 25)])
        assert np.array_equal(data[: len(expected)], expected)
        assert markers and markers[0].labels[0] == "cue rest"
