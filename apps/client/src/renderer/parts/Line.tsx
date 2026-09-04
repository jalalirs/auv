// One line of a plan: a label, what is chosen, and a list behind it.
//
// A dive is five choices, and each may have five things to choose from or
// five hundred — places as institutions publish them, controllers as people
// deploy them. A line shows the one chosen, whole: its picture, its name, one
// line about it, and a mark. Opening it drops a list under it with a search
// box, the same whether the list is short or long: rows to read, arrows and
// Enter to choose, Escape to leave, and what cannot be chosen yet at the
// bottom with its reason rather than hidden. Five of these stacked read as
// the plan — where, in what, flown by, in what water, for what — and the
// page stays five lines tall however much there is to choose from.

import { useEffect, useMemo, useRef, useState } from "react";

import type { Choice } from "./Picker.js";

export function Line({ label, choices, chosen, onChoose, onOpen, hint }: {
  label: string;
  choices: Choice[];
  chosen: string | undefined;
  onChoose: (key: string) => void;
  /** Open the chosen thing's own page. */
  onOpen?: (key: string) => void;
  /** A line under what is chosen, about what choosing it means. */
  hint?: React.ReactNode;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [lit, setLit] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const picked = choices.find((c) => c.key === chosen);

  // What the list shows: what matches, choosable first, in the order given.
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matching = q === "" ? choices
      : choices.filter((c) => `${c.name} ${c.says ?? ""} ${c.group ?? ""}`.toLowerCase().includes(q));
    return [...matching.filter((c) => c.later === undefined), ...matching.filter((c) => c.later !== undefined)];
  }, [choices, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setLit(Math.max(0, shown.findIndex((c) => c.key === chosen)));
    search.current?.focus();
    const away = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
    // Opening resets the list; what is chosen while it is open is the list's own business.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => { setLit(0); }, [query]);

  function choose(one: Choice): void {
    if (one.later !== undefined) return;
    onChoose(one.key);
    setOpen(false);
  }

  function keys(e: React.KeyboardEvent): void {
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setLit((i) => Math.min(shown.length - 1, i + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setLit((i) => Math.max(0, i - 1)); }
    if (e.key === "Enter") { e.preventDefault(); const one = shown[lit]; if (one) choose(one); }
  }

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLElement>(`.line-row[data-at="${lit}"]`)?.scrollIntoView({ block: "nearest" });
  }, [lit, open]);

  const groups = useMemo(() => {
    const seen = new Set<string>();
    return shown.map((c, i) => {
      const g = c.later !== undefined ? "not yet" : (c.group ?? "");
      if (seen.has(g)) return { at: i, choice: c, head: undefined };
      seen.add(g);
      return { at: i, choice: c, head: g === "" ? undefined : g };
    });
  }, [shown]);

  return (
    <div className={`line${open ? " open" : ""}`} ref={root} onKeyDown={keys}>
      <div className="line-label">{label}</div>
      <button type="button" className="line-chosen" aria-haspopup="listbox" aria-expanded={open}
              onClick={() => setOpen((o) => !o)}>
        {picked?.picture ? <img src={picked.picture} alt="" /> : <span className="line-blank" />}
        <span className="line-said">
          <strong>{picked?.name ?? "Choose…"}</strong>
          <span>{picked?.says ?? `${choices.filter((c) => c.later === undefined).length} to choose from`}</span>
        </span>
        {picked?.mark}
        <span className="line-count">{choices.length > 1 ? `${choices.length}` : ""}</span>
        <span className="line-chevron" aria-hidden="true">▾</span>
      </button>
      {picked && onOpen ? (
        <a className="line-open" title="Open its page" onClick={() => onOpen(picked.key)}>open ›</a>
      ) : <span />}
      {hint === undefined ? null : <div className="line-hint">{hint}</div>}

      {open ? (
        <div className="line-pop" role="listbox" aria-label={label}>
          {choices.length > 6 ? (
            <input ref={search} className="line-search" placeholder={`Search ${choices.length}…`}
                   value={query} onChange={(e) => setQuery(e.target.value)} />
          ) : null}
          <div className="line-rows">
            {shown.length === 0 ? <div className="line-none">nothing matches</div> : null}
            {groups.map(({ at, choice: one, head }) => (
              <div key={one.key}>
                {head === undefined ? null : <div className="line-head">{head}</div>}
                <div className={`line-row${one.key === chosen ? " chosen" : ""}${at === lit ? " lit" : ""}${one.later ? " later" : ""}`}
                     role="option" aria-selected={one.key === chosen} data-at={at}
                     onMouseEnter={() => setLit(at)} onClick={() => choose(one)}>
                  {one.picture ? <img src={one.picture} alt="" loading="lazy" /> : <span className="line-blank" />}
                  <span className="line-said">
                    <strong>{one.name}</strong>
                    {one.later ? <em>{one.later}</em> : one.says ? <span>{one.says}</span> : null}
                  </span>
                  {one.mark}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
