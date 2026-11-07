"""Built-in PyTorch architectures for ``safetensors`` state_dicts (requires the torch extra).

A state_dict holds tensors only; the code that uses them must come from somewhere trusted.
These are the architectures BrainOS provides, so a safetensors model never needs code from
its author. Declared in ``artifact.io``:

* ``{"architecture": "linear"}`` — ``y = W x + b`` (``torch.nn.Linear``), stateless.
* ``{"architecture": "gru", "hidden_size": n}`` — one-layer GRU over bins (state carried
  between steps) followed by a linear read-out: keys ``gru.*`` and ``readout.*``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from brainos_decoder_sdk.api import ModelLoadError

ARCHITECTURES = ("linear", "gru")
MAX_HIDDEN = 4096


def build(io: Mapping[str, Any], width: int, dims: int) -> tuple[Any, list[int] | None]:
    """(module, state shape or None) for the declared architecture."""
    import torch

    arch = io.get("architecture")
    if arch == "linear":
        return torch.nn.Linear(width, dims), None
    if arch == "gru":
        hidden = io.get("hidden_size")
        if isinstance(hidden, bool) or not isinstance(hidden, int) or not 0 < hidden <= MAX_HIDDEN:
            raise ModelLoadError(f"gru needs hidden_size in (0, {MAX_HIDDEN}], got {hidden!r}")
        return GRUReadout(width, hidden, dims), [1, 1, hidden]
    raise ModelLoadError(f"unknown architecture {arch!r}; available: {ARCHITECTURES}")


def _gru_class() -> type:
    import torch

    class _GRUReadout(torch.nn.Module):  # type: ignore[misc, unused-ignore]
        def __init__(self, width: int, hidden: int, dims: int) -> None:
            super().__init__()
            self.gru = torch.nn.GRU(width, hidden, batch_first=True)
            self.readout = torch.nn.Linear(hidden, dims)

        def forward(self, x: Any, h: Any) -> tuple[Any, Any]:
            y, h = self.gru(x[:, None, :], h)
            return self.readout(y[:, -1, :]), h

    return _GRUReadout


def GRUReadout(width: int, hidden: int, dims: int) -> Any:
    """A one-layer GRU + linear read-out: ``forward(x[1, width], h[1, 1, hidden])``."""
    return _gru_class()(width, hidden, dims)
