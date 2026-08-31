// Signing in to a platform.
//
// The address is asked for rather than assumed, because the platform is
// somebody's own box and there is no such thing as the one true Coral City. It
// is remembered between launches; the password never is.

import { useEffect, useRef, useState } from "react";

import { Platform, Refused, Unreachable } from "@coral-city/api";

import { Badge } from "./parts.js";

const REMEMBERED = "coral-city.platform";

export function SignIn({ onSignedIn }: {
  onSignedIn: (platform: Platform) => void;
}): React.JSX.Element {
  const [address, setAddress] = useState("");
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [trying, setTrying] = useState(false);
  const [refusal, setRefusal] = useState("");

  // Filled from a local file while this is being built, so that trying the
  // application does not begin with typing a forty-eight character secret.
  // The file is not in the repository and never should be; without it these are
  // empty and the form behaves as it will for everybody else.
  const waiting = import.meta.env.VITE_CORAL_CITY_PLATFORM as string | undefined;
  const known = import.meta.env.VITE_CORAL_CITY_EMAIL as string | undefined;
  const kept = import.meta.env.VITE_CORAL_CITY_SECRET as string | undefined;

  useEffect(() => {
    setAddress(waiting ?? localStorage.getItem(REMEMBERED) ?? "http://127.0.0.1:18080");
    if (known !== undefined) setEmail(known);
    if (kept !== undefined) setSecret(kept);
  }, [waiting, known, kept]);

  // And straight in, when all three are there. Signing in is not the part being
  // worked on, and having to do it by hand forty times an afternoon is how a
  // person stops trying the thing they are building.
  const went = useRef(false);
  useEffect(() => {
    if (went.current) return;
    if (waiting === undefined || known === undefined || kept === undefined) return;
    went.current = true;
    void (async () => {
      setTrying(true);
      try {
        onSignedIn(await Platform.signIn(waiting, known, kept));
      } catch (problem) {
        setRefusal(problem instanceof Unreachable
          ? `Nothing answered at ${waiting}.`
          : problem instanceof Refused ? problem.message : "That did not work.");
      } finally {
        setTrying(false);
      }
    })();
  }, [waiting, known, kept, onSignedIn]);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setTrying(true);
    setRefusal("");
    try {
      const platform = await Platform.signIn(address, email, secret);
      localStorage.setItem(REMEMBERED, platform.address);
      onSignedIn(platform);
    } catch (problem) {
      // A platform that is not there and a platform that said no are different
      // problems with different remedies, and telling somebody to check their
      // password when their laptop is offline wastes their afternoon.
      setRefusal(
        problem instanceof Unreachable
          ? `Nothing answered at ${address}. Is the box awake, and are you on its network?`
          : problem instanceof Refused
            ? problem.message
            : "That did not work.");
    } finally {
      setTrying(false);
    }
  }

  return (
    <div className="middle">
      <Badge under="Dive a vehicle you brought, in water we keep" />
      <form className="panel" onSubmit={submit}>
        <label>
          platform
          <input value={address} onChange={(e) => setAddress(e.target.value)}
                 placeholder="http://100.76.65.1:18080" spellCheck={false} />
        </label>
        <label>
          who you are
          <input value={email} onChange={(e) => setEmail(e.target.value)}
                 type="email" autoComplete="username" spellCheck={false} />
        </label>
        <label>
          secret
          <input value={secret} onChange={(e) => setSecret(e.target.value)}
                 type="password" autoComplete="current-password" />
        </label>
        <button disabled={trying || !address || !email || !secret}>
          {trying ? "Signing in…" : "Sign in"}
        </button>
        <p className="refusal">{refusal}</p>
      </form>
    </div>
  );
}
