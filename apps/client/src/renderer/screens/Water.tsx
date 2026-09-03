// In the water.
//
// An operator's console, not a video with two numbers on it. Four panes in the
// middle: the rendered water through whichever camera was asked for, the chart
// with the vehicle and its track, the last minute in section, and a plot of
// whichever topic was clicked. Any of the small ones swaps into the large slot
// when clicked. Around them, what the vehicle carries, who is flying it, and
// what it is doing.
//
// The keys are sent as the set currently held, not as presses and releases. A
// dropped press with that design leaves a thruster running until somebody
// notices; a dropped set is corrected forty milliseconds later by the next one.
// On a link that may lose a packet, state beats events.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Platform } from "@coral-city/api";

import type { Stream } from "../App.js";
import { Minimap, type Fix, type Geometry, type Site } from "../parts/Minimap.js";
import { Profile, type Moment } from "../parts/Profile.js";
import { TopicPlot, type Sample } from "../parts/TopicPlot.js";
import { Instruments, type Reading, type Topic } from "./instruments.js";

/** How often the keys held are sent, whether or not they changed. */
const TELL_EVERY = 40;

/** What the vehicle can be asked to do, and what asks for it. */
const FLYING = new Set(["W", "A", "S", "D", "Q", "E", "SPACE", "C"]);

/** How much of the recent past the plots keep. */
const REMEMBERED = 600;

/** How much of the track the chart keeps. */
const TRACKED = 4000;

/** The panes, and what each shows. */
export type Pane = "water" | "map" | "profile" | "plot";

const PANE_NAMES: Record<Pane, string> = {
  water: "water", map: "chart", profile: "section", plot: "plot",
};

interface Hello {
  kind: "hello";
  site?: Site | null;
  views?: string[];
  view?: string;
  beganAt?: number[];
  task?: { kind: string; name: string; geometry?: Geometry } | null;
}

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
  const [hello, setHello] = useState<Hello | undefined>();
  const [panes, setPanes] = useState<Pane[]>(["water", "map", "profile", "plot"]);
  const [plotted, setPlotted] = useState<string | undefined>();
  const [tick, setTick] = useState(0);
  const history = useRef<Moment[]>([]);
  const track = useRef<Fix[]>([]);
  const series = useRef<Map<string, Sample[]>>(new Map());
  const socketRef = useRef<WebSocket | undefined>(undefined);

  const say = useCallback((message: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
  }, []);
  /** Move one of a controller's parameters, and say so at once. */
  const tune = useCallback((controller: string, name: string, value: number) =>
    say({ tune: { controller, name, value } }), [say]);
  const holdHere = useCallback(() => say({ hold: "here" }), [say]);
  const engage = useCallback((controller: string) => say({ engage: controller }), [say]);
  const view = useCallback((which: string) => say({ view: which }), [say]);

  /** Swap a small pane into the large slot. */
  const enlarge = useCallback((pane: Pane) => {
    setPanes((was) => {
      const at = was.indexOf(pane);
      if (at <= 0) return was;
      const next = [...was];
      next[at] = was[0]!;
      next[0] = pane;
      return next;
    });
  }, []);

  /** Open a plot of a topic: choose it, and bring the plot forward. */
  const plot = useCallback((topic: string) => {
    setPlotted(topic);
    enlarge("plot");
  }, [enlarge]);

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
        const said = JSON.parse(message.data) as Reading & { kind?: string };
        if (said.kind === "hello") {
          setHello(said as unknown as Hello);
          return;
        }
        setReading(said);
        if (said.topics !== undefined) setTopics(said.topics);
        if (typeof said.t === "number") {
          history.current.push({
            t: said.t,
            depth: typeof said.depthM === "number" ? said.depthM : 0,
            speed: typeof said.speedMs === "number" ? said.speedMs : 0,
            floor: typeof said.floorM === "number" ? said.floorM : undefined,
          });
          if (history.current.length > REMEMBERED) history.current.shift();
          if (said.position !== undefined && said.position.length >= 2) {
            const last = track.current[track.current.length - 1];
            const x = said.position[0]!;
            const y = said.position[1]!;
            if (last === undefined || Math.hypot(last.x - x, last.y - y) > 0.02) {
              track.current.push({ x, y });
              if (track.current.length > TRACKED) track.current.shift();
            }
          }
          if (said.samples !== undefined) {
            for (const [topic, values] of Object.entries(said.samples)) {
              const kept = series.current.get(topic) ?? [];
              kept.push({ t: said.t, values });
              if (kept.length > REMEMBERED) kept.shift();
              series.current.set(topic, kept);
            }
          }
          setTick((n) => n + 1);
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
      socketRef.current = socket;
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

  const site = hello?.site ?? undefined;
  // The task's geometry, with what has been reached so far.
  const geometry: Geometry | undefined = hello?.task?.geometry === undefined ? undefined : {
    ...hello.task.geometry,
    reached: typeof reading.task?.detail["reached"] === "number" ? (reading.task.detail["reached"] as number) : hello.task.geometry.reached,
  };
  const views = hello?.views ?? ["chase", "front", "top", "orbit"];
  const looking = reading.view ?? hello?.view ?? "chase";

  function content(pane: Pane, large: boolean): React.JSX.Element {
    switch (pane) {
      case "water":
        return (
          <div className="viewport">
            <canvas ref={canvas} />
            {large ? (
              <div className="views">
                {views.map((one) => (
                  <button key={one} className={one === looking ? "on" : undefined}
                          onClick={(e) => { e.stopPropagation(); view(one); }}>
                    {one}
                  </button>
                ))}
              </div>
            ) : null}
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
        );
      case "map":
        return <Minimap site={site} track={track.current} position={reading.position}
                        headingDeg={reading.headingDeg} beganAt={hello?.beganAt}
                        geometry={geometry} large={large} />;
      case "profile":
        return <Profile of={history.current} />;
      case "plot":
        return <TopicPlot topic={plotted} of={plotted === undefined ? [] : (series.current.get(plotted) ?? [])} />;
    }
  }

  return (
    <Instruments reading={reading} topics={topics} held={held}
                 history={history.current} frames={frames} onLeave={leave}
                 onTune={tune} onHoldHere={holdHere} onEngage={engage} onPlot={plot}
                 plotted={plotted}>
      <div className="panes" data-tick={tick}>
        <div className="pane large">
          <span className="pane-name">{PANE_NAMES[panes[0]!]}</span>
          {content(panes[0]!, true)}
        </div>
        <div className="small-panes">
          {panes.slice(1).map((pane) => (
            <div key={pane} className="pane small" onClick={() => enlarge(pane)}
                 title={`show the ${PANE_NAMES[pane]} large`}>
              <span className="pane-name">{PANE_NAMES[pane]}</span>
              {content(pane, false)}
            </div>
          ))}
        </div>
      </div>
    </Instruments>
  );
}
