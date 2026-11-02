// iocean, from the outside in.
//
// Four states and no more, because that is how many the thing actually has: you
// are signed out, you are on the deck, you are waiting for water, or you are in
// it.

import { useCallback, useEffect, useState } from "react";

import { Platform, Refused } from "@coral-city/api";

import boot from "../../assets/boot.jpg";
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
  // Looking for the sign-in kept from before, until it is found or not.
  const [restoring, setRestoring] = useState(window.coralCity?.auth !== undefined);

  const signedIn = useCallback((into: Platform) => {
    setPlatform(into);
    setWhere({ at: "deck" });
    if (into.token !== undefined) void window.coralCity?.auth.keep({ base: into.address, token: into.token });
  }, []);

  const signOut = useCallback(() => {
    void window.coralCity?.auth.forget();
    setPlatform(undefined);
    setWhere({ at: "out" });
  }, []);

  // A kept session is used if the platform still honours it. Refused means it
  // ran out or was revoked, and it is forgotten; a platform that does not
  // answer keeps it for next time, and the person signs in meanwhile.
  useEffect(() => {
    const auth = window.coralCity?.auth;
    if (auth === undefined) return;
    void (async () => {
      const kept = await auth.kept();
      if (kept !== undefined) {
        const into = new Platform(kept.base, kept.token);
        try {
          await into.me();
          setPlatform(into);
          setWhere({ at: "deck" });
        } catch (problem) {
          if (problem instanceof Refused && problem.status === 401) void auth.forget();
        }
      }
      setRestoring(false);
    })();
  }, []);

  const surface = useCallback(() => setWhere({ at: "deck" }), []);

  return (
    <div className="sea">
      <div className="chrome" />
      {platform === undefined || where.at === "out" ? (
        restoring ? <div className="middle boot"><img className="boot-art" src={boot} alt="" /></div> : <SignIn onSignedIn={signedIn} />
      ) : where.at === "deck" ? (
        <Deck platform={platform} onSignOut={signOut}
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
