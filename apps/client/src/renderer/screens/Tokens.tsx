// Tokens a person makes for a program to act as them.
//
// For pointing an assistant — Claude, Codex, anything that speaks MCP — at this
// platform without handing it a sign-in secret. A token acts as the person who
// made it, with their grants as they are on every request; it is named after
// what will hold it, so a list of them can be read later; and it is revoked in
// one click when a laptop is lost or an experiment is over.
//
// The token is shown once, when it is made. It is not stored, so it cannot be
// shown again — only replaced — and this page says so rather than letting
// somebody close it and discover that afterwards.

import { useCallback, useEffect, useState } from "react";

import type { APIToken, Platform } from "@coral-city/api";

import { Empty } from "./parts.js";

/**
 * Where the MCP server is, from where the platform is.
 *
 * Two ways in, and the address follows whichever the app was signed into. The
 * public link — https://<name>.ts.net/coral — serves the platform's API and the
 * MCP server side by side under one path, so the MCP server is that address with
 * /mcp on the end. The raw ports on the tailnet put each on its own port, so
 * there it is the platform's host on 18083.
 */
export function mcpAddressFor(platformAddress: string | null): string {
  try {
    const at = new URL(platformAddress ?? "");
    if (at.port === "18080") return `${at.protocol}//${at.hostname}:18083/mcp`;
    return `${at.origin}${at.pathname.replace(/\/+$/, "")}/mcp`;
  } catch {
    return "https://<the platform>/mcp";
  }
}

/** The block to paste into an assistant's configuration, with the token in it. */
export function mcpConfig(address: string, token: string): string {
  return JSON.stringify({
    mcpServers: {
      "coral-city": {
        type: "http",
        url: address,
        headers: { Authorization: `Bearer ${token}` },
      },
    },
  }, null, 2);
}

function ago(when: string | undefined): string {
  if (!when) return "never";
  const seconds = (Date.now() - new Date(when).getTime()) / 1000;
  if (seconds < 90) return "just now";
  if (seconds < 3600 * 1.5) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400 * 1.5) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

export function Tokens({ platform }: { platform: Platform }): React.JSX.Element {
  const [tokens, setTokens] = useState<APIToken[] | undefined>();
  const [naming, setNaming] = useState("");
  const [made, setMade] = useState<{ name: string; token: string } | undefined>();
  const [copied, setCopied] = useState("");
  const [trouble, setTrouble] = useState("");

  const read = useCallback(() => {
    platform.tokens().then(setTokens)
      .catch((problem: unknown) => setTrouble(String((problem as Error)?.message ?? problem)));
  }, [platform]);
  useEffect(read, [read]);

  // From the session itself, not from what was remembered at sign-in. The
  // desktop application can come in by signing in automatically, which never
  // writes that key, and the page then offered `https://<the platform>/mcp` — a
  // placeholder somebody pasted into their assistant as though it were real.
  const address = mcpAddressFor(platform.address);

  const copy = (what: string, text: string) => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(what);
      setTimeout(() => setCopied(""), 1600);
    });
  };

  const live = (tokens ?? []).filter((t) => !t.revokedAt);
  const gone = (tokens ?? []).filter((t) => t.revokedAt);

  return (
    <section>
      <h2>Tokens for your assistant</h2>
      <p className="aside">
        Point Claude, Codex or anything that speaks MCP at {address} with one of
        these, and it acts as you — with what you may do now, not what you could
        when you made it. Name each after what will hold it.
      </p>

      {made ? (
        <div className="token-made">
          <div className="token-warning">
            <strong>Copy it now.</strong> This is the only time “{made.name}” is shown.
            It is not stored, so it cannot be shown again — only replaced.
          </div>
          <div className="token-row">
            <code className="token-value">{made.token}</code>
            <button type="button" onClick={() => copy("token", made.token)}>
              {copied === "token" ? "Copied" : "Copy token"}
            </button>
          </div>
          <div className="token-row">
            <pre className="token-config">{mcpConfig(address, made.token)}</pre>
            <button type="button" onClick={() => copy("config", mcpConfig(address, made.token))}>
              {copied === "config" ? "Copied" : "Copy MCP config"}
            </button>
          </div>
          <button type="button" className="quiet" onClick={() => setMade(undefined)}>
            I have kept it
          </button>
        </div>
      ) : null}

      <form className="naming" onSubmit={(event) => {
        event.preventDefault();
        const name = naming.trim();
        if (!name) return;
        setTrouble("");
        void platform.makeToken(name).then((said) => {
          setMade({ name, token: said.token });
          setNaming("");
          read();
        }).catch((problem: unknown) => setTrouble(String((problem as Error)?.message ?? problem)));
      }}>
        <input value={naming} onChange={(e) => setNaming(e.target.value)}
               placeholder="name it after what will hold it — “my Claude”" />
        <button type="submit" disabled={!naming.trim()}>Make a token</button>
      </form>
      {trouble ? <p className="refusal">{trouble}</p> : null}

      {tokens === undefined ? null : live.length === 0 && gone.length === 0 ? (
        <Empty title="No tokens yet">
          Make one above, paste the MCP config it gives you into your assistant,
          and it can read places, plan dives and fly them as you.
        </Empty>
      ) : (
        <div className="ledger">
          {[...live, ...gone].map((one) => (
            <div className={`row token${one.revokedAt ? " revoked" : ""}`} key={one.id ?? one.prefix}>
              <code className="token-prefix">{one.prefix}…</code>
              <strong>{one.name}</strong>
              <span className="when">
                made {ago(one.createdAt)} · used {ago(one.lastUsedAt)}
                {one.expiresAt ? ` · ends ${new Date(one.expiresAt).toLocaleDateString()}` : ""}
                {one.revokedAt ? ` · revoked ${ago(one.revokedAt)}` : ""}
              </span>
              {one.revokedAt ? <span className="pill">revoked</span> : (
                <button type="button" className="quiet" onClick={() => {
                  void platform.revokeToken(one.id ?? "").then(read)
                    .catch((problem: unknown) => setTrouble(String((problem as Error)?.message ?? problem)));
                }}>Revoke</button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
