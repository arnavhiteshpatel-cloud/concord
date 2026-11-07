"""A sender that reproduces BCI2000's ConnectorOutput byte for byte, for edge-case tests.

Reproduces ``src/shared/modules/application/ConnectorFilters.cpp`` (BCI2000 3.6):

* ``ConnectorOutput::Process`` lines 224-229: for each state in StateList order
  ``name << ' ' << State(name) << '\\n'`` (a ``uint32_t``), then for each channel and element
  ``"Signal(" << channel << "," << element << ") " << Input(channel, element) << '\\n'``
  (a ``double`` with default ostream formatting = ``%g``, 6 significant digits).
* ``ConnectorOutput::Connection::OnExecute`` lines 252-260: every line is one datagram.

Real BCI2000 output (``fixtures/bci2000_connector_output.json``) shows the StateList order
for SignalGenerator + DummySignalProcessing + DummyApplication: Notes, Recording,
SourceTime, StimulusTime, SourceChannel1, FilePart, Running, then added states, then
``__pad0``.. ``__pad3``.
"""

from __future__ import annotations

import math
import socket
from collections.abc import Iterable, Sequence

DEFAULT_STATES = (
    "Notes",
    "Recording",
    "SourceTime",
    "StimulusTime",
    "SourceChannel1",
    "FilePart",
    "Running",
    "TargetCode",
    "ResultCode",
    "Feedback",
    "__pad0",
    "__pad1",
    "__pad2",
    "__pad3",
)


def ostream_double(value: float) -> str:
    """``std::ostream << double`` with default flags: like printf ``%g``."""
    if math.isnan(value):
        return "nan" if math.copysign(1.0, value) > 0 else "-nan"
    return f"{value:g}"


def block_lines(
    states: Sequence[tuple[str, int]], signal: Sequence[Sequence[float]]
) -> list[bytes]:
    lines = [f"{name} {value & 0xFFFFFFFF}\n".encode("ascii") for name, value in states]
    for ch, row in enumerate(signal):
        for el, v in enumerate(row):
            lines.append(f"Signal({ch},{el}) {ostream_double(v)}\n".encode("ascii"))
    return lines


class Sender:
    """Sends datagrams to the plugin like ConnectorOutput's sending thread."""

    def __init__(self, port: int, host: str = "127.0.0.1") -> None:
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, datagrams: Iterable[bytes]) -> int:
        n = 0
        for d in datagrams:
            self.sock.sendto(d, self.addr)
            n += 1
        return n

    def close(self) -> None:
        self.sock.close()


def free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port
