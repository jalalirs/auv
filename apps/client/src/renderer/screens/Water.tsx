// In the water.
//
// Frames come down and keys go up, over one socket. Nothing else is on this
// screen: you are looking at a place through a vehicle, and every panel added
// here is water taken away.
//
// The keys are sent as the set that is currently held, not as presses and
// releases. A dropped press with that design leaves a thruster running until
// somebody notices, whereas a dropped set is corrected by the next one forty
// milliseconds later. On a link that may lose a packet, state beats events.

import { useEffect, useRef, useState } from "react";

import type { Stream } from "../App.js";

/** How often the keys held are sent, whether or not they changed. */
const TELL_EVERY = 40;

/** What the vehicle can be asked to do, and what asks for it. */
const FLYING = new Set(["W", "A", "S", "D", "Q", "E", "SPACE", "C"]);

function named(event: KeyboardEvent): string | undefined {
  if (event.code === "Space") return "SPACE";
  if (event.code.startsWith("Key")) {
    const letter = event.code.slice(3);
    return FLYING.has(letter) ? letter : undefined;
  }
  return undefined;
}

export function Water({ stream, onSurface }: {
  stream: Stream;
  onSurface: () => void;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<Record<string, unknown>>({});
  const [lost, setLost] = useState<string | undefined>();

  useEffect(() => {
    const held = new Set<string>();
    const socket = new WebSocket(`ws://${stream.host}:${stream.signalPort}/watch`);
    socket.binaryType = "blob";

    const down = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onSurface(); return; }
      const key = named(event);
      if (key !== undefined) { held.add(key); event.preventDefault(); }
    };
    const up = (event: KeyboardEvent) => {
      const key = named(event);
      if (key !== undefined) held.delete(key);
    };
    // Letting go of the window lets go of the controls. A vehicle that kept
    // thrusting because somebody switched to their mail is a vehicle that hits
    // the wall of the tank.
    const blur = () => held.clear();

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);

    const tell = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ held: [...held] }));
      }
    }, TELL_EVERY);

    socket.onmessage = async (message) => {
      if (typeof message.data === "string") {
        setState(JSON.parse(message.data));
        return;
      }
      const picture = await createImageBitmap(message.data as Blob);
      const surface = canvas.current;
      if (surface === null) { picture.close(); return; }
      if (surface.width !== picture.width) surface.width = picture.width;
      if (surface.height !== picture.height) surface.height = picture.height;
      surface.getContext("2d")?.drawImage(picture, 0, 0);
      picture.close();
    };
    socket.onerror = () => setLost("The dive stopped answering.");
    socket.onclose = () => setLost((was) => was ?? "The dive ended.");

    return () => {
      clearInterval(tell);
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
      socket.close();
    };
  }, [stream, onSurface]);

  const depth = state.depthM;
  const speed = state.speedMs;

  return (
    <>
      <div className="viewport">
        <canvas ref={canvas} />
        <div className="hud">
          <div className="reading">
            <span>depth</span>
            <strong>{typeof depth === "number" ? `${depth.toFixed(2)} m` : "—"}</strong>
          </div>
          <div className="reading">
            <span>speed</span>
            <strong>{typeof speed === "number" ? `${speed.toFixed(2)} m/s` : "—"}</strong>
          </div>
          <div className="keys">WASD move · Q E turn · SPACE C rise, dive · ESC surface</div>
        </div>
        {lost === undefined ? null : (
          <div className="lost">
            <h2>{lost}</h2>
            <button className="quiet" onClick={onSurface}>Back</button>
          </div>
        )}
      </div>
    </>
  );
}
