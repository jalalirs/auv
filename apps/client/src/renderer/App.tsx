// Coral City, from the outside in.
//
// Four states and no more, because that is how many the thing actually has:
// you are signed out, you are choosing, you are waiting for water, or you are
// in it. Every screen below is one of those.

import { useCallback, useState } from "react";

import { Platform } from "@coral-city/api";

import { Choosing } from "./screens/Choosing.js";
import { SignIn } from "./screens/SignIn.js";
import { Water } from "./screens/Water.js";
import { Waiting } from "./screens/Waiting.js";

/** Where a dive is being watched, once the platform says it is running. */
export interface Stream {
  host: string;
  signalPort: number;
  streamPort: number;
  diveId: string;
  runId: string;
}

type Where =
  | { at: "out" }
  | { at: "choosing" }
  | { at: "waiting"; dive: string; run: string }
  | { at: "water"; stream: Stream };

export function App(): React.JSX.Element {
  const [platform, setPlatform] = useState<Platform | undefined>();
  const [where, setWhere] = useState<Where>({ at: "out" });

  const signedIn = useCallback((into: Platform) => {
    setPlatform(into);
    setWhere({ at: "choosing" });
  }, []);

  const leave = useCallback(() => setWhere({ at: "choosing" }), []);

  return (
    <div className="sea">
      <div className="chrome" />
      {platform === undefined || where.at === "out" ? (
        <SignIn onSignedIn={signedIn} />
      ) : where.at === "choosing" ? (
        <Choosing
          platform={platform}
          onAsked={(dive, run) => setWhere({ at: "waiting", dive, run })}
        />
      ) : where.at === "waiting" ? (
        <Waiting
          platform={platform}
          dive={where.dive}
          run={where.run}
          onRunning={(stream) => setWhere({ at: "water", stream })}
          onGiveUp={leave}
        />
      ) : (
        <Water stream={where.stream} onSurface={leave} />
      )}
    </div>
  );
}
