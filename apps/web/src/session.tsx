import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { client, Refused, type Organisation, type Principal } from "@coral-city/client";

import { navigate } from "./router";

/**
 * Who is signed in.
 *
 * There is no anonymous read (ADR-0006), so the whole application sits behind
 * this: until the platform says who the caller is, there is nothing to show.
 */
interface Session {
  principal: Principal;
  organisations: Organisation[];
}

interface SessionState {
  status: "checking" | "signed-out" | "signed-in";
  session?: Session;
  signIn: (email: string, secret: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionState | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionState["status"]>("checking");
  const [session, setSession] = useState<Session | undefined>();

  const load = useCallback(async () => {
    try {
      const me = await client.me();
      setSession({ principal: me.principal, organisations: me.organisations });
      setStatus("signed-in");
    } catch (error) {
      if (error instanceof Refused && error.unauthenticated) {
        setSession(undefined);
        setStatus("signed-out");
        return;
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const value = useMemo<SessionState>(
    () => ({
      status,
      session,
      signIn: async (email, secret) => {
        await client.signIn(email, secret);
        await load();
      },
      signOut: async () => {
        await client.signOut();
        setSession(undefined);
        setStatus("signed-out");
        navigate("/");
      },
    }),
    [status, session, load],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const state = useContext(SessionContext);
  if (!state) {
    throw new Error("useSession was called outside a SessionProvider");
  }
  return state;
}
