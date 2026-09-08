"""A controller's slow clock: somewhere to think that is not the flight loop.

Flying happens at the physics rate — sixty times a second, every step, no
exceptions and no waiting. Deciding does not. Working out where to go next may
take a second, may want the network, may call a model, and may come back with
nothing at all. Those two things cannot share a clock, and until now there was
only the fast one: any controller that paused to think stopped the vehicle,
which is why every controller here is arithmetic.

So a controller may declare a second, slower loop. It runs on its own thread,
one thought at a time, and the flight loop never waits for it: it keeps flying
whatever it last decided. When a thought comes back it is handed over on the
flight thread, between steps, so a controller never has to think about locks.

What this costs is counted rather than hidden. A thought that takes two seconds
is two seconds during which the vehicle is acting on older information, and it
is charged in simulated seconds — a dive with a thinking controller does not
run faster than the clock on the wall, because a brain that is slow in reality
must be slow here or the benchmark is a lie.

What can go wrong is recorded rather than fatal: a thought that raises is
counted and dropped, a thought that takes longer than its patience is
abandoned, and either way the vehicle is still flying the last good one.
"""

from __future__ import annotations

import threading
import time


class Thinking:
    """The slow loop for one controller, and the record of how it went."""

    def __init__(self, controller, patience: float = 20.0) -> None:
        self.controller = controller
        # How long a thought may take before it is abandoned. Generous,
        # because the point is to allow slow thinking; a controller that wants
        # a tighter budget can enforce its own.
        self.patience = float(patience)
        self._thread: threading.Thread | None = None
        self._done: list[tuple[float, object]] = []      # (asked at, what it decided)
        self._failed: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self.asked_at: float | None = None               # simulated time of the request
        self.started_at: float = 0.0                     # wall clock, for the latency
        self.last_at: float | None = None                # when the last thought landed
        self.thoughts = 0
        self.failures = 0
        self.abandoned = 0
        self.latencies: list[float] = []

    # ── the flight loop's side ───────────────────────────────────────────────

    def tick(self, seen) -> None:
        """Called every step: take delivery of a thought, and ask for another."""
        self._deliver()
        self._maybe_ask(seen)

    def _deliver(self) -> None:
        with self._lock:
            done, self._done = self._done, []
            failed, self._failed = self._failed, []
        for asked_at, decided in done:
            self.thoughts += 1
            self.last_at = asked_at
            if decided is None:
                continue
            try:
                self.controller.on_thought(decided)
            except Exception as exc:                     # a controller's own fault
                self.failures += 1
                self._say(f"applying a thought failed: {exc}")
        for _asked_at, why in failed:
            self.failures += 1
            self._say(why)

    def _maybe_ask(self, seen) -> None:
        every = getattr(self.controller, "thinks_every", None)
        if not every:
            return
        if self._thread is not None and self._thread.is_alive():
            if time.monotonic() - self.started_at > self.patience:
                # Still going, long past its welcome. It is left to finish and
                # its answer will be thrown away, because a thread that cannot
                # be interrupted is better forgotten than waited for.
                self.abandoned += 1
                self._thread = None
            else:
                return
        if self.asked_at is not None and seen.t - self.asked_at < float(every):
            return
        self.asked_at = seen.t
        self.started_at = time.monotonic()
        thread = threading.Thread(target=self._think, args=(seen, seen.t), daemon=True,
                                  name=f"thinking-{self.controller.name}")
        self._thread = thread
        thread.start()

    # ── the slow loop's side ─────────────────────────────────────────────────

    def _think(self, seen, at: float) -> None:
        began = time.monotonic()
        try:
            decided = self.controller.think(seen)
        except Exception as exc:
            with self._lock:
                self._failed.append((at, f"a thought raised: {type(exc).__name__}: {exc}"))
            return
        took = time.monotonic() - began
        with self._lock:
            self.latencies.append(took)
            self._done.append((at, decided))

    def _say(self, why: str) -> None:
        self.trouble = why[:200]

    # ── what is reported ─────────────────────────────────────────────────────

    def said(self) -> dict:
        latest = self.latencies[-1] if self.latencies else None
        return {
            "thoughts": self.thoughts,
            "failures": self.failures,
            "abandoned": self.abandoned,
            "thinking": self._thread is not None and self._thread.is_alive(),
            "lastS": None if latest is None else round(latest, 3),
            "slowestS": None if not self.latencies else round(max(self.latencies), 3),
            "meanS": None if not self.latencies
                     else round(sum(self.latencies) / len(self.latencies), 3),
            **({"trouble": self.trouble} if getattr(self, "trouble", None) else {}),
        }
