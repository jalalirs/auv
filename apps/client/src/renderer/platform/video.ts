// Decoding the dive's picture, when it is sent as video rather than pictures.
//
// A JPEG a frame is the whole reef again twenty times a second — eleven
// megabits, which is nothing on the same network and a slideshow from a hotel.
// The dive can send H.264 instead, which is the same picture at about a
// megabit and a half because the reef does not change much between frames.
//
// This is the other end of that: WebCodecs, which the application has because
// it is Chromium, handed whole access units as they arrive. A watcher that
// cannot do this says nothing and is sent pictures, so nothing has to be
// configured and nothing breaks on a machine without the codec.
//
// Frames are drawn and closed at once. Holding on to a VideoFrame is holding a
// GPU buffer, and a handful of leaked ones will stop the decoder dead.

/** Whether this machine can decode what the dive offers to send. */
export function canDecode(): boolean {
  return typeof globalThis.VideoDecoder === "function";
}

export interface Video {
  /** One access unit off the socket. */
  take(packet: ArrayBuffer): void;
  close(): void;
  /** What it has decoded, and what it has thrown away waiting for a keyframe. */
  said(): { frames: number; waited: number; bytes: number };
}

export function decodeInto(canvas: HTMLCanvasElement, onFrame: () => void): Video {
  const ink = canvas.getContext("2d");
  let started = false;         // a stream must begin at a keyframe or not at all
  let frames = 0;
  let waited = 0;
  let bytes = 0;

  const decoder = new VideoDecoder({
    output: (frame) => {
      try {
        if (ink !== null) {
          if (canvas.width !== frame.displayWidth) canvas.width = frame.displayWidth;
          if (canvas.height !== frame.displayHeight) canvas.height = frame.displayHeight;
          ink.drawImage(frame, 0, 0);
        }
        frames += 1;
        onFrame();
      } finally {
        frame.close();
      }
    },
    error: () => { started = false; },
  });

  // Annex B, which is what comes out of the encoder: no description, and the
  // parameter sets travel in the stream with every keyframe.
  decoder.configure({ codec: "avc1.42E01E", optimizeForLatency: true });

  return {
    take(packet: ArrayBuffer): void {
      // Two bytes in front: a mark, and whether this one stands on its own.
      const head = new Uint8Array(packet, 0, 2);
      const key = head[1] === 1;
      const unit = new Uint8Array(packet, 2);
      bytes += unit.byteLength;
      if (!started && !key) {
        // Nothing before the first keyframe can be decoded, and feeding it
        // anyway is how a decoder ends up in a state it will not leave.
        waited += 1;
        return;
      }
      started = true;
      try {
        decoder.decode(new EncodedVideoChunk({
          type: key ? "key" : "delta",
          timestamp: performance.now() * 1000,
          data: unit,
        }));
      } catch {
        started = false;
      }
    },
    close(): void {
      try { decoder.close(); } catch { /* already gone */ }
    },
    said() {
      return { frames, waited, bytes };
    },
  };
}
