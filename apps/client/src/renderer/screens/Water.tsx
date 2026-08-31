// In the water.
//
// An operator's console, not a video with two numbers on it. What is on screen
// is what somebody flying a vehicle actually needs: what the vehicle carries
// and whether anything is crossing it, what it is doing right now, what it has
// been doing for the last minute, and the water itself in the middle of it.
//
// The keys are sent as the set currently held, not as presses and releases. A
// dropped press with that design leaves a thruster running until somebody
// notices; a dropped set is corrected forty milliseconds later by the next one.
// On a link that may lose a packet, state beats events.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Platform } from "@coral-city/api";

import type { Stream } from "../App.js";
import { Instruments, type Reading, type Topic } from "./instruments.js";

/** How often the keys held are sent, whether or not they changed. */
const TELL_EVERY = 40;

/** What the vehicle can be asked to do, and what asks for it. */
const FLYING = new Set(["W", "A", "S", "D", "Q", "E", "SPACE", "C"]);

/** How much of the recent past the plots keep. */
const REMEMBERED = 600;

function named(event: KeyboardEvent): string | undefined {
  if (event.code === "Space") return "SPACE";
  if (event.code.startsWith("Key")) {
    const letter = event.code.slice(3);
    return FLYING.has(letter) ? letter : undefined;
  }
  return undefined;
}

export function Water({ platform, stream, onSurface }: {
  platform: Platform;
  stream: Stream;
  onSurface: () => void;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [reading, setReading] = useState<Reading>({});
  const [topics, setTopics] = useState<Topic[]>([]);
  const [held, setHeld] = useState<string[]>([]);
  const [lost, setLost] = useState<string | undefined>();
  const [frames, setFrames] = useState(0);
  const history = useRef<{ t: number; depth: number; speed: number }[]>([]);

  /**
   * Leaving ends the dive, and gives the machine back.
   *
   * Not merely navigating away. A dive holds a GPU somebody else is queued for,
   * and one abandoned by closing a window held it for its full hour.
   */
  const leave = useCallback(() => {
    void platform.cancel(stream.diveId, stream.runId).catch(() => {
      // Already over, or unreachable. Neither is worth saying to somebody who
      // has decided to leave.
    });
    onSurface();
  }, [platform, stream, onSurface]);

  useEffect(() => {
    const down = new Set<string>();
    let socket: WebSocket | undefined;
    let attempts = 0;
    let giveUpAt = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let done = false;

    const onDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { leave(); return; }
      const key = named(event);
      if (key !== undefined) { down.add(key); setHeld([...down]); event.preventDefault(); }
    };
    const onUp = (event: KeyboardEvent) => {
      const key = named(event);
      if (key !== undefined) { down.delete(key); setHeld([...down]); }
    };
    // Letting go of the window lets go of the controls. A vehicle still
    // thrusting because somebody switched to their mail is a vehicle in a wall.
    const blur = () => { down.clear(); setHeld([]); };

    const closing = () => {
      navigator.sendBeacon?.(
        `${platform.address}/api/v1/dives/${stream.diveId}/runs/${stream.runId}/cancel`);
    };

    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", blur);
    window.addEventListener("pagehide", closing);

    const tell = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ held: [...down] }));
      }
    }, TELL_EVERY);

    const onMessage = async (message: MessageEvent) => {
      if (typeof message.data === "string") {
        const said = JSON.parse(message.data) as Reading;
        setReading(said);
        if (said.topics !== undefined) setTopics(said.topics);
        if (typeof said.t === "number") {
          history.current.push({
            t: said.t,
            depth: typeof said.depthM === "number" ? said.depthM : 0,
            speed: typeof said.speedMs === "number" ? said.speedMs : 0,
          });
          if (history.current.length > REMEMBERED) history.current.shift();
        }
        return;
      }
      const picture = await createImageBitmap(message.data as Blob);
      const surface = canvas.current;
      if (surface === null) { picture.close(); return; }
      if (surface.width !== picture.width) surface.width = picture.width;
      if (surface.height !== picture.height) surface.height = picture.height;
      surface.getContext("2d")?.drawImage(picture, 0, 0);
      picture.close();
      setFrames((n) => n + 1);
    };

    // Retried rather than given up on. A socket refused once is usually a dive
    // that has not finished opening its scene, which takes a minute.
    function again(): void {
      if (done) return;
      if (giveUpAt === 0) giveUpAt = Date.now() + 120_000;
      if (Date.now() > giveUpAt) { setLost("The dive never answered."); return; }
      attempts += 1;
      retry = setTimeout(connect, Math.min(1000 * attempts, 4000));
    }

    function connect(): void {
      if (done) return;
      socket = new WebSocket(`ws://${stream.host}:${stream.signalPort}/watch`);
      socket.binaryType = "blob";
      socket.onopen = () => { giveUpAt = 0; attempts = 0; setLost(undefined); };
      socket.onmessage = onMessage;
      socket.onerror = () => { /* close follows, and carries the decision */ };
      socket.onclose = again;
    }

    connect();

    return () => {
      done = true;
      clearInterval(tell);
      if (retry !== undefined) clearTimeout(retry);
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("blur", blur);
      window.removeEventListener("pagehide", closing);
      socket?.close();
    };
  }, [stream, leave, platform]);

  return (
    <Instruments reading={reading} topics={topics} held={held}
                 history={history.current} frames={frames} onLeave={leave}>
      <div className="viewport">
        <canvas ref={canvas} />
        {frames === 0 && lost === undefined && (
          <div className="opening">
            <div className="tide" />
            <p>Opening the scene…</p>
          </div>
        )}
        {lost !== undefined && (
          <div className="lost">
            <h2>{lost}</h2>
            <button className="quiet" onClick={leave}>Surface</button>
          </div>
        )}
      </div>
    </Instruments>
  );
}
