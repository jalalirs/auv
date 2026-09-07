"""Turning frames into something that fits down a long link.

A JPEG a frame is the simplest thing that works and the most expensive thing
to send. Every frame carries the whole reef again, at sixty kilobytes and
twenty a second — eleven megabits — and on the same network that is invisible
and from a hotel it is a slideshow.

Video codecs exist for exactly this: the reef does not change between frames,
so send what changed. The card in this machine has an encoder on it that does
nothing else, and it turns the same picture into something like a megabit and
a half without touching the processor the simulation is using.

The pipe is ffmpeg, fed raw frames on its input and read for Annex-B on its
output. Not a library binding, because the binding for this encoder is not in
this image and a subprocess that can be replaced by a person reading its
command line is worth more than one that cannot. Frames are dropped rather
than queued when the encoder is behind, since a late frame of a live picture
is of no use to anybody.

What comes out is handed over one access unit at a time, with a byte saying
whether it can be decoded on its own, so a watcher joining late knows to wait
for the next one.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading

import carb

# Where a NAL starts, and the kinds that matter.
START = b"\x00\x00\x00\x01"
ACCESS_UNIT = 9        # the delimiter that says a new picture begins here
KEYFRAME = 5           # an IDR: decodable without anything before it
SEQUENCE = 7           # SPS, which comes with the keyframe


class Encoder:
    """Frames in, H.264 access units out."""

    def __init__(self, wide: int, tall: int, fps: int, on_packet=None, say=None,
                 bitrate: str = "1200k", peak: str = "1800k", into=None) -> None:
        self.wide, self.tall, self.fps = wide, tall, fps
        # Where it goes: to a callback, packet by packet, for a watcher on a
        # socket; or into a file, for a recording somebody will play back.
        self.into = None if into is None else str(into)
        self.on_packet = on_packet
        self.say = say
        self.bitrate, self.peak = bitrate, peak
        self.process: subprocess.Popen | None = None
        self.reader: threading.Thread | None = None
        self.codec = ""
        self.sent = 0
        self.written = 0
        self.dropped = 0
        self.bytes = 0
        # Frames are handed over rather than written here. A frame is four
        # megabytes and a pipe holds sixty-four kilobytes, so writing one from
        # the thread that is running the simulation stops the simulation until
        # the encoder has caught up — which, at eight frames of a dive per
        # second of it, stops it altogether.
        self._waiting: queue.Queue = queue.Queue(maxsize=2)
        self._writer: threading.Thread | None = None
        self._buffer = bytearray()
        self._headers = b""

    # ── the pipe ─────────────────────────────────────────────────────────────

    @staticmethod
    def available() -> bool:
        return shutil.which("ffmpeg") is not None

    def start(self) -> bool:
        """Open the encoder. The card's if it will have us, the processor's if not."""
        if self.process is not None:
            return True
        if not self.available():
            self.say("video_unavailable", why="no ffmpeg in this image")
            return False
        for codec, options in (
            # Low latency, no B-frames, a keyframe every two seconds so a
            # watcher arriving late waits no longer than that.
            ("h264_nvenc", ["-preset", "p1", "-tune", "ll", "-zerolatency", "1", "-rc", "cbr"]),
            ("libx264", ["-preset", "ultrafast", "-tune", "zerolatency"]),
        ):
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "bgra",
                "-s", f"{self.wide}x{self.tall}", "-r", str(self.fps), "-i", "-",
                "-an", "-c:v", codec, *options,
                "-b:v", self.bitrate, "-maxrate", self.peak, "-bufsize", "300k",
                "-g", str(self.fps * 2), "-bf", "0",
                "-pix_fmt", "yuv420p",
            ]
            if self.into is None:
                # To a socket: delimited, so whole pictures can be told apart.
                command += ["-aud", "1", "-f", "h264", "-"]
            else:
                # To a file a browser can seek in: the index at the front, so
                # it can be played before it has finished downloading.
                command += ["-movflags", "+faststart", "-f", "mp4", self.into]
            try:
                self.process = subprocess.Popen(
                    command, stdin=subprocess.PIPE,
                    stdout=None if self.into is not None else subprocess.PIPE,
                    stderr=subprocess.PIPE, bufsize=0)
            except Exception as exc:
                carb.log_warn(f"Coral City could not start {codec}: {exc}")
                continue
            # It may still fail on the first frame — an encoder session it
            # cannot get, a driver that will not have it — and the reader
            # notices that and says so.
            self.codec = codec
            self._writer = threading.Thread(target=self._feed, name="coral.video.in", daemon=True)
            self._writer.start()
            if self.into is None:
                self.reader = threading.Thread(target=self._read, name="coral.video", daemon=True)
                self.reader.start()
            self.say("video_open", codec=codec, wide=self.wide, tall=self.tall,
                     fps=self.fps, bitrate=self.bitrate)
            return True
        return False

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            # Let the writer finish what it has before the input is closed,
            # or the last second of the recording is not in it.
            for _ in range(50):
                if self._waiting.empty():
                    break
                threading.Event().wait(0.05)
            if process.stdin:
                process.stdin.close()
            if self.into is not None:
                # A file has to be finished: the index is written when the
                # encoder is allowed to close, and a killed encoder leaves a
                # video nothing will play.
                try:
                    process.wait(timeout=20)
                except Exception:
                    process.terminate()
                return
            process.terminate()
        except Exception:
            pass

    # ── frames ───────────────────────────────────────────────────────────────

    def write(self, frame: bytes) -> None:
        """One raw BGRA frame, handed to the writer. Never blocks the caller."""
        if self.process is None:
            return
        try:
            self._waiting.put_nowait(frame)
        except queue.Full:
            # A late frame of a live picture is no use, and a dropped one of a
            # recording is an eighth of a second. Either beats stopping the
            # simulation to wait for an encoder.
            self.dropped += 1

    def _feed(self) -> None:
        """Frames into the encoder, on a thread of their own."""
        while True:
            frame = self._waiting.get()
            process = self.process
            if frame is None or process is None or process.stdin is None:
                return
            try:
                # Every byte of it, in a loop. An unbuffered pipe writes what
                # fits and says how much that was; ignoring the answer tears
                # the frame in half and hands the encoder two of somebody
                # else's.
                at, whole = 0, len(frame)
                while at < whole:
                    wrote = process.stdin.write(frame[at:])
                    if not wrote:
                        break
                    at += wrote
                self.written += 1
            except (BrokenPipeError, ValueError, OSError) as exc:
                self.say("video_stopped", why=str(exc)[:120], sent=self.sent)
                self.process = None
                return

    def _read(self) -> None:
        """Annex-B out of the encoder, split into whole pictures."""
        process = self.process
        if process is None or process.stdout is None:
            return
        while True:
            chunk = process.stdout.read(16384)
            if not chunk:
                break
            self._buffer.extend(chunk)
            self._cut()
        if self.process is process:
            trouble = b""
            try:
                trouble = process.stderr.read() if process.stderr else b""
            except Exception:
                pass
            self.say("video_ended", codec=self.codec, sent=self.sent,
                     why=trouble.decode("utf-8", "ignore")[-160:] or "the encoder closed")
            self.process = None

    def _cut(self) -> None:
        """Hand over every complete access unit the buffer now holds.

        An access unit begins at a delimiter, which the encoder is asked to
        write for exactly this reason: without one, finding where one picture
        ends and the next begins means parsing slice headers, and this is a
        console rather than a demuxer.
        """
        while True:
            first = self._buffer.find(START + bytes([ACCESS_UNIT]))
            if first < 0:
                return
            second = self._buffer.find(START + bytes([ACCESS_UNIT]), first + 5)
            if second < 0:
                return
            # From the start of the buffer, not from the delimiter. The
            # encoder writes the sequence and picture parameter sets *before*
            # the delimiter of the keyframe they belong to, and cutting at the
            # delimiter threw them away — which is a stream no decoder can
            # start, and it says so as "non-existing PPS".
            unit = bytes(self._buffer[:second])
            del self._buffer[:second]
            self._hand_over(unit)

    def _hand_over(self, unit: bytes) -> None:
        kinds = set()
        at = 0
        while True:
            at = unit.find(START, at)
            if at < 0 or at + 4 >= len(unit):
                break
            kinds.add(unit[at + 4] & 0x1F)
            at += 4
        key = KEYFRAME in kinds
        if SEQUENCE in kinds:
            # Keep the parameter sets themselves — not the picture they came
            # with — so a keyframe that arrives without them can be given
            # them, and a watcher joining halfway has something to start on.
            self._headers = self._parameter_sets(unit)
        elif key and self._headers:
            unit = self._headers + unit
        self.sent += 1
        self.bytes += len(unit)
        self.on_packet(unit, key)

    @staticmethod
    def _parameter_sets(unit: bytes) -> bytes:
        """Just the sequence and picture parameter sets out of an access unit."""
        kept = bytearray()
        at = unit.find(START)
        while at >= 0:
            nxt = unit.find(START, at + 4)
            end = len(unit) if nxt < 0 else nxt
            if at + 4 < len(unit) and (unit[at + 4] & 0x1F) in (SEQUENCE, 8):
                kept.extend(unit[at:end])
            at = nxt
        return bytes(kept)

    def said(self) -> dict:
        return {"codec": self.codec, "into": self.into,
                "packets": self.sent, "framesIn": self.written,
                "bytes": self.bytes,
                "droppedFrames": self.dropped,
                "kbPerSecond": None if self.sent == 0
                else round(self.bytes / max(1, self.sent) * self.fps / 1024.0, 1)}
