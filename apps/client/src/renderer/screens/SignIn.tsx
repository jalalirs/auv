// Signing in to a platform.
//
// The address is asked for rather than assumed, because the platform is
// somebody's own box and there is no such thing as the one true Coral City. It
// is remembered between launches; the password never is.

import { useEffect, useState } from "react";

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

  useEffect(() => {
    setAddress(localStorage.getItem(REMEMBERED) ?? "http://127.0.0.1:18080");
  }, []);

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
