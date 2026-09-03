"""The window somebody watches a dive through, and the controls they fly it with.

One socket, both directions: frames down, the keys being held up. It is our own
protocol rather than the streaming stack Kit ships, and that is a decision worth
justifying rather than assuming.

The alternative was Omniverse's WebRTC livestream, which is better video than
this. But its client is NVIDIA's application, distributed as a binary, and the
library that speaks to it is not something we can put inside our own. Using it
means the thing a person opens to dive is somebody else's program with somebody
else's name on it, and the platform's own application becomes a launcher for it.
That is the wrong shape for a product, and no amount of better compression fixes
it.

So: frames as JPEG over a websocket. It is honest about what it is — an image
pipe — and it is ours end to end, which means the client is ours, the input path
is ours, and the whole thing can be replaced with a hardware-encoded video
stream later without the application on somebody's laptop changing at all. The
socket is the contract; what travels over it can improve.
"""

from __future__ import annotations

import asyncio
import json
import threading

import carb

# What is sent, and how often. 960x540 at twenty frames is comfortably enough to
# fly a vehicle by and small enough to cross a domestic link; the encoder is the
# cost here, not the wire.
WIDE, TALL = 960, 540
FRAMES_PER_SECOND = 20
QUALITY = 72


class Watch:
    """Serves the dive to whoever is watching it."""

    def __init__(self, port: int, controls, say, on_message=None, on_hello=None) -> None:
        self.port = port
        self.controls = controls
        self.say = say
        # Anything the watcher asks for that is not steering — a parameter
        # moved, the hold re-engaged, a view, a controller — goes to whoever
        # owns the dive.
        self.on_message = on_message
        # What somebody arriving needs once: the site to draw a map from, the
        # vehicle, the views there are.
        self.on_hello = on_hello
        # Each watcher's socket, and the queue its sender drains.
        self.watchers: dict = {}
        self._loop = None
        self._latest = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    # ── the socket ───────────────────────────────────────────────────────────

    def _serve(self) -> None:
        """A server on its own thread, so nothing here can stall the physics.

        The simulation loop must not wait on a network. A watcher on a slow
        link should see fewer frames, not make the vehicle fly differently.
        """
        try:
            from aiohttp import web
        except ImportError as exc:  # a dive nobody can watch is still a dive
            self.say("watch_unavailable", why=str(exc))
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        async def watch(request):
            socket = web.WebSocketResponse(heartbeat=20)
            await socket.prepare(request)
            if self.on_hello is not None:
                try:
                    await socket.send_str(json.dumps(self.on_hello()))
                except Exception as exc:
                    carb.log_warn(f"Coral City could not greet a watcher: {exc}")
            # One sender per watcher, fed a queue that holds only the newest
            # frame. Sending straight from the capture callback put every
            # frame on the wire as its own coroutine, and on a link slower
            # than the renderer two of them interleaved mid-frame — which a
            # browser answers by dropping the connection. A watcher on a slow
            # link now sees fewer frames, each whole, and the newest.
            latest: asyncio.Queue = asyncio.Queue(maxsize=1)
            self.watchers[socket] = latest
            sender = asyncio.ensure_future(self._deliver(socket, latest))
            self.say("watcher_arrived", watching=len(self.watchers))
            try:
                async for message in socket:
                    if message.type == web.WSMsgType.TEXT:
                        self._hands(message.data)
            finally:
                self.watchers.pop(socket, None)
                sender.cancel()
                # Nobody watching is nobody at the controls. A vehicle left
                # thrusting because a laptop lid closed is a vehicle in the wall.
                if not self.watchers:
                    self.controls.let_go()
                self.say("watcher_left", watching=len(self.watchers))
            return socket

        application = web.Application()
        application.router.add_get("/watch", watch)

        runner = web.AppRunner(application)
        loop.run_until_complete(runner.setup())
        # On every interface of the container, which has no route off the host
        # except the one port the agent published.
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        loop.run_until_complete(site.start())
        self.say("watch_open", port=self.port, wide=WIDE, tall=TALL,
                 framesPerSecond=FRAMES_PER_SECOND)
        loop.run_forever()

    def _hands(self, raw: str) -> None:
        """What the person watching is holding down.

        The whole set each time rather than presses and releases. A dropped
        press leaves a thruster running until somebody notices; a dropped set is
        corrected forty milliseconds later by the next one.
        """
        try:
            said = json.loads(raw)
            if "held" in said:
                self.controls.held_from_afar(set(said.get("held", [])))
            if "stick" in said:
                self.controls.stick_from_afar(said.get("stick") or [])
            if self.on_message is not None and any(
                    key in said for key in ("tune", "hold", "view", "engage")):
                self.on_message(said)
        except Exception as exc:
            carb.log_warn(f"Coral City could not read what was asked: {exc}")

    # ── sending ──────────────────────────────────────────────────────────────

    async def _deliver(self, socket, latest: asyncio.Queue) -> None:
        """Drain one watcher's queue onto its socket, one frame at a time."""
        try:
            while True:
                jpeg, payload = await latest.get()
                await socket.send_bytes(jpeg)
                await socket.send_str(payload)
        except asyncio.CancelledError:
            return
        except Exception:
            self.watchers.pop(socket, None)

    def send(self, jpeg: bytes, state: dict) -> None:
        """Hand a frame to the watchers. Never blocks the caller."""
        if self._loop is None or not self.watchers:
            return
        payload = json.dumps(state)

        def offer():
            for latest in list(self.watchers.values()):
                # The newest frame replaces one nobody has taken yet.
                if latest.full():
                    try:
                        latest.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    latest.put_nowait((jpeg, payload))
                except asyncio.QueueFull:
                    pass

        self._loop.call_soon_threadsafe(offer)

    @property
    def watched(self) -> bool:
        return bool(self.watchers)

    def close(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
