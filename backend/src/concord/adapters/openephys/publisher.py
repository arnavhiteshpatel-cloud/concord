"""TEST PUBLISHER — a protocol-faithful software stand-in for the Open Ephys ZMQ Interface.

**This is not Open Ephys.** It emits exactly the messages the plugin's source code
(``zmq-interface@38513917``, ``Source/ZmqInterface.cpp``) emits, built by
:mod:`concord.adapters.openephys.protocol`, so that the adapter can be tested end-to-end
over real ZMQ sockets without the GUI:

* PUB socket on ``data_port``; per block: queued TTL events and spikes first (the plugin
  calls ``checkForEvents`` before sending data), then one ``data`` message per selected
  channel, all with the block's first ``sample_num``;
* REP socket on ``data_port + 1`` that answers like ``ZmqInterface::run``
  ("heartbeat received" / "message correctly parsed" / "JSON message could not be read")
  and records the clients it has seen;
* ``message_num`` reset to 0 at (re)start of acquisition, first message is 1.

The signal comes from a callback, so tests can feed known values and other code can feed
recorded data. Fault injection: dropped messages, dropped channel blocks, raw (malformed)
frames, pause/resume of acquisition, channel/sample-rate changes, stop.

It binds ``127.0.0.1`` by default; it never listens on all interfaces unless told to.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import zmq

from concord.adapters.openephys.protocol import (
    TTL_EVENT_TYPE,
    encode_data,
    encode_event,
    encode_spike,
    encode_ttl_payload,
    heartbeat_reply,
)

#: (first sample_num, num_samples, channel_nums) -> array [len(channel_nums)][num_samples]
SignalFn = Callable[[int, int, tuple[int, ...]], npt.ArrayLike]


def ramp_signal(sample_num: int, num_samples: int, channels: tuple[int, ...]) -> npt.ArrayLike:
    """Deterministic, float32-exact test signal: ``channel*1000 + (sample % 4096) * 0.25``."""
    t = (np.arange(sample_num, sample_num + num_samples, dtype=np.int64) % 4096) * 0.25
    return np.asarray([ch * 1000.0 + t for ch in channels], dtype=np.float32)


@dataclass(slots=True)
class ClientRecord:
    application: str
    uuid: str
    requests: int = 0
    heartbeats: int = 0
    events: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class OpenEphysTestPublisher:
    """Background-thread stand-in for the plugin (see module docstring)."""

    def __init__(
        self,
        *,
        data_port: int,
        host: str = "127.0.0.1",
        stream: str = "example_data",
        sample_rate: float = 30_000.0,
        channels: Sequence[int] = tuple(range(8)),
        channel_names: Sequence[str] | None = None,
        block_size: int = 1024,
        signal: SignalFn | None = None,
        speed: float = 1.0,
        acquiring: bool = True,
        source_node: int = 100,
        sndhwm: int = 100_000,
    ) -> None:
        if block_size < 1:
            raise ValueError("block_size must be >= 1")
        self.data_port = data_port
        self.host = host
        self.stream = stream
        self.sample_rate = float(sample_rate)
        self.block_size = block_size
        self.signal: SignalFn = signal or ramp_signal
        self.speed = speed  # 1.0 = real time; 0 = as fast as possible
        self.source_node = source_node
        self.sndhwm = sndhwm
        self._channels: tuple[int, ...] = ()
        self._names: tuple[str, ...] = ()
        self._set_channels(channels, channel_names)
        self.acquiring = acquiring
        self.sample_num = 0
        self.message_num = 0
        self.blocks_sent = 0
        self.messages_sent = 0
        self.messages_dropped = 0
        #: (kind, sample_num, detail) of every TTL/spike built, in send order
        self.sent_log: list[tuple[str, int, str]] = []
        self.clients: dict[str, ClientRecord] = {}
        self.requests: list[bytes] = []
        self.replies: list[bytes] = []
        self._commands: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._pending_events: list[tuple[int, Callable[[int], list[bytes]]]] = []
        self._pub: zmq.Socket[bytes] | None = None
        self._drop_next = 0
        self._drop_channel: dict[int, int] = {}
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- lifecycle
    def start(self) -> OpenEphysTestPublisher:
        self._thread = threading.Thread(target=self._run, name="oe-test-publisher", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error is not None:
            raise self._error
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> OpenEphysTestPublisher:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------- control (any thread)
    @property
    def channels(self) -> tuple[int, ...]:
        return self._channels

    @property
    def channel_names(self) -> tuple[str, ...]:
        return self._names

    def start_acquisition(self, *, reset: bool = True) -> None:
        """Like the GUI's start: ``message_num`` (and, by default, the sample clock) reset."""

        def cmd() -> None:
            if reset:
                self.message_num = 0
                self.sample_num = 0
            self.acquiring = True

        self._commands.put(cmd)

    def reset_sample_clock(self, to: int = 0) -> None:
        """Like the GUI's File Reader looping: sample numbers restart while acquisition (and
        ``message_num``) continue. Not an acquisition restart."""

        def cmd() -> None:
            self.sample_num = to

        self._commands.put(cmd)

    def stop_acquisition(self) -> None:
        def cmd() -> None:
            self.acquiring = False

        self._commands.put(cmd)

    def set_channels(self, channels: Sequence[int], names: Sequence[str] | None = None) -> None:
        """Change the channel selection (takes effect at the next block)."""
        self._commands.put(lambda: self._set_channels(channels, names))

    def set_sample_rate(self, rate: float) -> None:
        def cmd() -> None:
            self.sample_rate = float(rate)

        self._commands.put(cmd)

    def drop_messages(self, n: int) -> None:
        """The next ``n`` messages consume a message_num but are not sent (loss)."""

        def cmd() -> None:
            self._drop_next += n

        self._commands.put(cmd)

    def drop_channel_blocks(self, channel_num: int, n: int = 1) -> None:
        """Lose ``channel_num``'s message in the next ``n`` blocks (message_num still advances)."""

        def cmd() -> None:
            self._drop_channel[channel_num] = self._drop_channel.get(channel_num, 0) + n

        self._commands.put(cmd)

    def send_raw(self, frames: Sequence[bytes]) -> None:
        """Send arbitrary frames now (malformed-input injection); no message_num consumed."""
        raw = [bytes(f) for f in frames]
        self._commands.put(lambda: self._send(raw))

    def send_ttl(
        self,
        line: int,
        state: int,
        word: int = 0,
        *,
        offset: int = 0,
        sample_num: int | None = None,
    ) -> None:
        """Queue a TTL event, sent with the next block (sample = block start + offset)."""
        payload = encode_ttl_payload(line, state, word)

        def build(s: int) -> list[bytes]:
            self.message_num += 1
            self.sent_log.append(("ttl", s, f"line={line} state={state} word={word}"))
            return encode_event(
                message_num=self.message_num,
                stream=self.stream,
                source_node=self.source_node,
                event_type=TTL_EVENT_TYPE,
                sample_num=s,
                payload=payload,
                timestamp_ms=int(time.time() * 1000),
            )

        self._commands.put(
            lambda: self._pending_events.append((self._abs(offset, sample_num), build))
        )

    def send_spike(
        self,
        electrode: str,
        *,
        offset: int = 0,
        sample_num: int | None = None,
        waveform: npt.ArrayLike | None = None,
        sorted_id: int = 0,
        threshold: Sequence[float] | None = None,
    ) -> None:
        """Queue a spike, sent with the next block (before its data, like the plugin)."""
        wf = np.asarray(
            waveform if waveform is not None else np.full((1, 40), -50.0), dtype=np.float32
        )
        thr = list(threshold) if threshold is not None else [-50.0] * wf.shape[0]

        def build(s: int) -> list[bytes]:
            self.message_num += 1
            self.sent_log.append(("spike", s, electrode))
            return encode_spike(
                message_num=self.message_num,
                stream=self.stream,
                source_node=self.source_node,
                electrode=electrode,
                sample_num=s,
                sorted_id=sorted_id,
                threshold=thr,
                waveform=wf,
                timestamp_ms=int(time.time() * 1000),
            )

        self._commands.put(
            lambda: self._pending_events.append((self._abs(offset, sample_num), build))
        )

    def call(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the publisher thread before the next block."""
        self._commands.put(fn)

    # ------------------------------------------------------------ thread side
    def _abs(self, offset: int, sample_num: int | None) -> int:
        return sample_num if sample_num is not None else self.sample_num + offset

    def _set_channels(self, channels: Sequence[int], names: Sequence[str] | None) -> None:
        chans = tuple(int(c) for c in channels)
        nms = tuple(names) if names is not None else tuple(f"CH{c + 1}" for c in chans)
        if len(nms) != len(chans):
            raise ValueError("one name per channel")
        self._channels, self._names = chans, nms

    def _send(self, frames: list[bytes]) -> None:
        assert self._pub is not None
        self._pub.send_multipart(frames, copy=False)
        self.messages_sent += 1

    def _emit(self, frames: list[bytes]) -> None:
        if self._drop_next > 0:
            self._drop_next -= 1
            self.messages_dropped += 1
            return
        self._send(frames)

    def _send_block(self) -> None:
        start, n = self.sample_num, self.block_size
        events, self._pending_events = self._pending_events, []
        for s, build in sorted(events, key=lambda e: e[0]):
            self._emit(build(s))
        data = np.asarray(self.signal(start, n, self._channels), dtype=np.float32)
        if data.shape != (len(self._channels), n):
            raise ValueError(
                f"signal returned shape {data.shape}, expected {(len(self._channels), n)}"
            )
        ts = int(time.time() * 1000)
        for i, (ch, name) in enumerate(zip(self._channels, self._names, strict=True)):
            self.message_num += 1
            frames = encode_data(
                message_num=self.message_num,
                stream=self.stream,
                channel_num=ch,
                channel_name=name,
                sample_num=start,
                sample_rate=self.sample_rate,
                samples=data[i],
                timestamp_ms=ts,
            )
            if self._drop_channel.get(ch, 0) > 0:
                self._drop_channel[ch] -= 1
                self.messages_dropped += 1
                continue
            self._emit(frames)
        self.sample_num = start + n
        with self._lock:
            self.blocks_sent += 1

    def _serve_rep(self, rep: zmq.Socket[bytes]) -> None:
        request = rep.recv()
        reply = heartbeat_reply(request)
        rep.send(reply)
        self.requests.append(request)
        self.replies.append(reply)
        try:
            v = json.loads(request)
        except ValueError:
            return
        if not isinstance(v, dict):
            return
        uid = str(v.get("uuid", ""))
        rec = self.clients.get(uid)
        if rec is None:
            rec = self.clients[uid] = ClientRecord(str(v.get("application", "")), uid)
        rec.requests += 1
        rec.last_seen = time.time()
        if v.get("type") == "event":
            rec.events += 1
        else:
            rec.heartbeats += 1

    def _run(self) -> None:
        ctx: zmq.Context[zmq.Socket[bytes]] = zmq.Context()
        pub = ctx.socket(zmq.PUB)
        rep = ctx.socket(zmq.REP)
        self._pub = pub
        try:
            for s in (pub, rep):
                s.setsockopt(zmq.LINGER, 0)
            pub.setsockopt(zmq.SNDHWM, self.sndhwm)
            pub.bind(f"tcp://{self.host}:{self.data_port}")
            rep.bind(f"tcp://{self.host}:{self.data_port + 1}")
        except BaseException as exc:
            self._error = exc
            pub.close(0)
            rep.close(0)
            ctx.term()
            self._ready.set()
            return
        self._ready.set()
        poller = zmq.Poller()
        poller.register(rep, zmq.POLLIN)
        next_due = time.monotonic()
        try:
            while not self._stop.is_set():
                while True:
                    try:
                        self._commands.get_nowait()()
                    except queue.Empty:
                        break
                now = time.monotonic()
                if self.acquiring:
                    wait = max(0.0, next_due - now) if self.speed > 0 else 0.0
                else:
                    wait = 0.02
                for sock, _ in poller.poll(timeout=round(wait * 1000)):
                    self._serve_rep(sock)
                if not self.acquiring:
                    next_due = time.monotonic()
                    continue
                now = time.monotonic()
                if self.speed <= 0 or now >= next_due:
                    self._send_block()
                    period = (
                        self.block_size / self.sample_rate / self.speed if self.speed > 0 else 0
                    )
                    next_due += period
                    if now - next_due > 5 * period:  # fell far behind: resync, don't burst
                        next_due = now
        except BaseException as exc:  # surfaced to the test via .error
            self._error = exc
            raise
        finally:
            self._pub = None
            pub.close(0)
            rep.close(0)
            ctx.term()

    @property
    def error(self) -> BaseException | None:
        return self._error

    def client_summary(self) -> dict[str, Any]:
        return {u: (c.application, c.heartbeats) for u, c in self.clients.items()}
