import { useState } from "react";
import { Refused } from "@coral-city/client";

import { useSession } from "../session";

export function SignIn() {
  const { signIn } = useSession();
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [refusal, setRefusal] = useState<string | undefined>();
  const [working, setWorking] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setWorking(true);
    setRefusal(undefined);
    try {
      await signIn(email, secret);
    } catch (error) {
      // An unknown address and a wrong secret are refused identically, so this
      // message says neither which it was nor whether the address is known.
      setRefusal(
        error instanceof Refused && error.unauthenticated
          ? "Those credentials do not identify anyone."
          : "The platform could not be reached.",
      );
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="signin">
      <form onSubmit={(event) => void submit(event)}>
        <h1>Coral City</h1>
        <p className="quiet">
          One shared, governed record of the ocean. Nothing here is readable
          without signing in.
        </p>

        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="username" required
               value={email} onChange={(event) => setEmail(event.target.value)} />

        <label htmlFor="secret">Secret</label>
        <input id="secret" type="password" autoComplete="current-password" required
               value={secret} onChange={(event) => setSecret(event.target.value)} />

        {refusal ? <p className="form-refusal" role="alert">{refusal}</p> : null}

        <button type="submit" disabled={working}>
          {working ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
