// Coral City, from the outside in.
//
// Four states and no more, because that is how many the thing actually has: you
// are signed out, you are on the deck, you are waiting for water, or you are in
// it.

import { useCallback, useState } from "react";

import { Platform } from "@coral-city/api";

import { Deck } from "./screens/Deck.js";
import { SignIn } from "./screens/SignIn.js";
import { Water } from "./screens/Water.js";
import { Waiting } from "./screens/Waiting.js";

/** Where a dive is being watched, once the platform says it is running. */
export interface Stream {
  host: string;
  signalPort: number;
  diveId: string;
  runId: string;
}

type Where =
  | { at: "out" }
  | { at: "deck" }
  | { at: "waiting"; dive: string; run: string }
  | { at: "water"; stream: Stream };

export function App(): React.JSX.Element {
  const [platform, setPlatform] = useState<Platform | undefined>();
  const [where, setWhere] = useState<Where>({ at: "out" });

  const signedIn = useCallback((into: Platform) => {
    setPlatform(into);
    setWhere({ at: "deck" });
  }, []);

  const surface = useCallback(() => setWhere({ at: "deck" }), []);

  return (
    <div className="sea">
      <div className="chrome" />
      {platform === undefined || where.at === "out" ? (
        <SignIn onSignedIn={signedIn} />
      ) : where.at === "deck" ? (
        <Deck platform={platform}
              onDiving={(dive, run) => setWhere({ at: "waiting", dive, run })} />
      ) : where.at === "waiting" ? (
        <Waiting platform={platform} dive={where.dive} run={where.run}
                 onRunning={(stream) => setWhere({ at: "water", stream })}
                 onGiveUp={surface} />
      ) : (
        <Water platform={platform} stream={where.stream} onSurface={surface} />
      )}
    </div>
  );
}
