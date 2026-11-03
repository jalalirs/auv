// The parts every page is made of (docs/ui.md).
//
// A page is a fixed head (where it sits, its title in one line, its one
// primary action, its tabs, its toolbar) over a body that scrolls on its own.
// Buttons come in three kinds and two sizes; a row's lesser actions live in
// its ⋯ menu; a list longer than a screen is a Table, which searches,
// filters with counts, sorts and pages, and drops columns rather than
// scrolling sideways when the window is narrow or zoomed.

import { useEffect, useMemo, useRef, useState } from "react";

// ── buttons ────────────────────────────────────────────────────────────────

export type ButtonKind = "primary" | "secondary" | "ghost" | "danger";

export function Button({ kind = "secondary", size, icon, children, className, ...rest }: {
  kind?: ButtonKind;
  size?: "large";
  icon?: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>): React.JSX.Element {
  return (
    <button type="button" {...rest}
            className={`btn btn-${kind}${size === "large" ? " btn-large" : ""}${className ? ` ${className}` : ""}`}>
      {icon ? <span className="btn-icon" aria-hidden>{icon}</span> : null}
      {children}
    </button>
  );
}

// ── a row's lesser actions ─────────────────────────────────────────────────

export type MenuItem = { label: string; onSelect: () => void; danger?: boolean; disabled?: boolean };

export function Menu({ items, label = "More" }: { items: MenuItem[]; label?: string }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape); };
  }, [open]);
  return (
    <div className="menu" ref={box} onClick={(e) => e.stopPropagation()}>
      <button type="button" className="btn btn-ghost btn-square" aria-label={label} aria-expanded={open}
              onClick={() => setOpen((o) => !o)}>⋯</button>
      {open ? (
        <div className="menu-list" role="menu">
          {items.map((item) => (
            <button key={item.label} type="button" role="menuitem" disabled={item.disabled}
                    className={item.danger ? "danger" : undefined}
                    onClick={() => { setOpen(false); item.onSelect(); }}>
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ── the page ───────────────────────────────────────────────────────────────

export type Tab = { key: string; label: string; count?: number };

export function Page({ title, subtitle, info, crumb, onCrumb, actions, tabs, tab, onTab, toolbar, wide, fill, status, children }: {
  title: React.ReactNode;
  /** One line about the page, read from the info mark beside the title. */
  subtitle?: React.ReactNode;
  info?: React.ReactNode;
  /** Where Back goes, by name: the step before the title in the path. */
  crumb?: string;
  onCrumb?: () => void;
  actions?: React.ReactNode;
  tabs?: Tab[];
  tab?: string;
  onTab?: (key: string) => void;
  /** Controls for what the body shows: a row under the bar that does not
   *  scroll away, with the page's own New at its start. */
  toolbar?: React.ReactNode;
  /** Full width; otherwise the body is held to a readable measure. */
  wide?: boolean;
  /** The body is one workspace edge to edge: no padding, no scroll of its own. */
  fill?: boolean;
  /** Quiet words at the bar's end, before the actions: saved, running. */
  status?: React.ReactNode;
  children: React.ReactNode;
}): React.JSX.Element {
  // One thin bar: where you are as a path, then what you can do. The page's
  // own explanation is behind the mark beside its name, never a paragraph
  // across the top of the work.
  const about = subtitle || info ? <>{subtitle ? <p>{subtitle}</p> : null}{info ? <p>{info}</p> : null}</> : null;
  return (
    <div className="page">
      <header className="bar">
        {crumb ? (
          <button type="button" className="back" onClick={onCrumb} aria-label={`Back to ${crumb}`} title={`Back to ${crumb}`}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        ) : null}
        <div className="path" role="navigation" aria-label="Where you are">
          {crumb ? <><button type="button" className="crumb" onClick={onCrumb}>{crumb}</button><span className="sep">/</span></> : null}
          <h1>{title}</h1>
          {about ? <Info>{about}</Info> : null}
        </div>
        {tabs ? (
          <div className="tabs" role="tablist">
            {tabs.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={t.key === tab}
                      onClick={() => onTab?.(t.key)}>
                {t.label}{t.count !== undefined ? <span className="tab-count">{t.count.toLocaleString()}</span> : null}
              </button>
            ))}
          </div>
        ) : null}
        <span className="bar-gap" />
        {status ? <span className="bar-status">{status}</span> : null}
        {actions ? <div className="page-actions">{actions}</div> : null}
      </header>
      {/* The page's tools stay where they are while what they filter scrolls. */}
      {toolbar ? <div className="page-tools">{toolbar}</div> : null}
      <div className={`page-body${wide ? " wide" : ""}${fill ? " whole" : ""}`}>
        {children}
      </div>
    </div>
  );
}

/** One of a few views of the same thing, side by side. Not for different kinds of thing. */
export function Segmented<K extends string>({ options, value, onChange, label }: {
  options: { key: K; label: React.ReactNode; count?: number }[];
  value: K;
  onChange: (key: K) => void;
  label?: string;
}): React.JSX.Element {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={o.key === value} onClick={() => onChange(o.key)}>
          {o.label}{o.count !== undefined ? <small>{o.count.toLocaleString()}</small> : null}
        </button>
      ))}
    </div>
  );
}

/** What a page or a figure is, for whoever asks: a small (i) that opens. */
export function Info({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <span className="info" onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-label="About this" onClick={() => setOpen((o) => !o)}>i</button>
      {open ? <span className="info-pop" role="tooltip">{children}</span> : null}
    </span>
  );
}

// ── a dialog ───────────────────────────────────────────────────────────────

export function Dialog({ title, onClose, actions, wide, children }: {
  title: string;
  onClose: () => void;
  actions?: React.ReactNode;
  /** Room for a map or a picture, not only fields. */
  wide?: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  return (
    <div className="dialog-shade" onMouseDown={onClose}>
      <div className={`dialog${wide ? " wide" : ""}`} role="dialog" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <div className="dialog-body">{children}</div>
        {actions ? <div className="dialog-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

// ── a state, as a word with a colour ────────────────────────────────────────

export type Tone = "good" | "bad" | "busy" | "warn" | "quiet";

export function Status({ tone = "quiet", children }: { tone?: Tone; children: React.ReactNode }): React.JSX.Element {
  return <span className={`status status-${tone}`}>{children}</span>;
}

// ── what is coming, while it comes ──────────────────────────────────────────

/** A grey shape where something will be, with a light passing over it. Sized
 *  like what replaces it, so the page does not jump when it arrives. */
export function Skeleton({ width, height, round, className }: {
  width?: number | string; height?: number | string; round?: boolean; className?: string;
}): React.JSX.Element {
  return <span className={`skeleton${round ? " round" : ""}${className ? ` ${className}` : ""}`}
               style={{ width, height }} aria-hidden="true" />;
}

/** Lines of text still on their way: the last one shorter, as text is. */
export function SkeletonLines({ lines = 3 }: { lines?: number }): React.JSX.Element {
  return (
    <div className="skeleton-lines" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} width={i === lines - 1 ? "60%" : "100%"} />)}
    </div>
  );
}

/** Cards still on their way, in the grid the real ones will fill. */
export function SkeletonCards({ count = 6, className = "cards" }: { count?: number; className?: string }): React.JSX.Element {
  return (
    <div className={className} aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton-card">
          <Skeleton height={120} />
          <Skeleton width="70%" height={16} />
          <Skeleton width="45%" />
        </div>
      ))}
    </div>
  );
}

// ── a list longer than a screen ─────────────────────────────────────────────

export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => React.ReactNode;
  /** Sorts by this column when its head is clicked. */
  sort?: (a: T, b: T) => number;
  align?: "right";
  /** 1 always shown; 2 dropped below 900 px of table; 3 below 1150 px. */
  priority?: 1 | 2 | 3;
  width?: string;
  /** Takes (a share of) the room the others leave, its text clipped with
   *  an ellipsis (the first column, unless others say). */
  grow?: boolean;
};

export type Facet<T> = { key: string; label: string; value: (row: T) => string | undefined };

export function Table<T>({ rows, columns, rowKey, onRow, search, searchLabel = "Search", facets = [], actions,
                           pageSize = 25, empty, initialSort, chosen, initialPicked, loading, tally, lead }: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRow?: (row: T) => void;
  /** The text a row is searched by. */
  search?: (row: T) => string;
  searchLabel?: string;
  facets?: Facet<T>[];
  /** A row's own actions, at its end: a primary button and a Menu at most. */
  actions?: (row: T) => React.ReactNode;
  pageSize?: number;
  empty?: React.ReactNode;
  initialSort?: { key: string; down?: boolean };
  chosen?: string;
  /** Filters set on arrival, by facet key: "Its dives" from Controllers. */
  initialPicked?: Record<string, string[]>;
  /** Still being read: rows of placeholders under the real column heads. */
  loading?: boolean;
  /** What the count counts, when a row is more than one thing (a dive flown
   *  five times is one row and five dives): the rows' total and its noun. */
  tally?: { count: (rows: T[]) => number; noun: string };
  /** The page's own New, at the start of the tools, before the search. */
  lead?: React.ReactNode;
}): React.JSX.Element {
  const [words, setWords] = useState("");
  const [picked, setPicked] = useState<Record<string, Set<string>>>(() =>
    Object.fromEntries(Object.entries(initialPicked ?? {}).map(([k, v]) => [k, new Set(v)])));
  const [sort, setSort] = useState<{ key: string; down: boolean } | undefined>(
    initialSort ? { key: initialSort.key, down: initialSort.down ?? false } : undefined);
  const [page, setPage] = useState(0);

  const facetValues = useMemo(() => facets.map((f) => {
    const counts = new Map<string, number>();
    for (const r of rows) { const v = f.value(r); if (v) counts.set(v, (counts.get(v) ?? 0) + 1); }
    return { facet: f, counts: [...counts.entries()].sort((a, b) => b[1] - a[1]) };
  }), [rows, facets]);

  const shown = useMemo(() => {
    const terms = words.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let out = rows.filter((r) => {
      for (const f of facets) {
        const want = picked[f.key];
        if (want && want.size > 0 && !want.has(f.value(r) ?? "")) return false;
      }
      if (terms.length && search) {
        const text = search(r).toLowerCase();
        return terms.every((t) => text.includes(t));
      }
      return true;
    });
    const col = sort && columns.find((c) => c.key === sort.key);
    if (col?.sort) {
      out = [...out].sort(col.sort);
      if (sort!.down) out.reverse();
    }
    return out;
  }, [rows, facets, picked, words, search, sort, columns]);

  useEffect(() => { setPage(0); }, [words, picked, sort]);
  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const at = Math.min(page, pages - 1);
  const slice = shown.slice(at * pageSize, at * pageSize + pageSize);
  const filtering = words.trim() !== "" || Object.values(picked).some((s) => s.size > 0);
  // One column takes the slack and clips its words, so a long description
  // never pushes the row's actions off the side of the page.
  const grows = new Set(columns.some((c) => c.grow) ? columns.filter((c) => c.grow).map((c) => c.key) : [columns[0]?.key]);
  const cls = (c: Column<T>) => `${c.align === "right" ? "right " : ""}p${c.priority ?? 1}${grows.has(c.key) ? " grow" : ""}`;

  return (
    <div className={`dt${grows.size === 1 ? " one-grows" : ""}`}>
      {search || facets.length || lead ? (
        <div className="dt-tools">
          {lead}
          {search ? (
            <input className="dt-search" type="search" value={words} placeholder={searchLabel}
                   onChange={(e) => setWords(e.target.value)} />
          ) : null}
          {facetValues.map(({ facet, counts }) => (
            <FacetPicker key={facet.key} label={facet.label} counts={counts} picked={picked[facet.key] ?? new Set()}
                         onChange={(next) => setPicked((was) => ({ ...was, [facet.key]: next }))} />
          ))}
          {filtering ? (
            <Button kind="ghost" onClick={() => { setWords(""); setPicked({}); }}>Clear</Button>
          ) : null}
          <span className="dt-count">{tally
            ? `${filtering ? `${tally.count(shown).toLocaleString()} of ` : ""}${tally.count(rows).toLocaleString()} ${tally.noun}`
            : filtering ? `${shown.length.toLocaleString()} of ${rows.length.toLocaleString()}` : rows.length.toLocaleString()}</span>
        </div>
      ) : null}
      {loading && rows.length === 0 ? (
        <table aria-busy="true">
          <thead>
            <tr>
              {columns.map((c) => <th key={c.key} className={cls(c)} style={c.width ? { width: c.width } : undefined}>{c.label}</th>)}
              {actions ? <th className="dt-actions" /> : null}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 6 }, (_, i) => (
              <tr key={i} className="dt-skeleton">
                {columns.map((c, j) => (
                  <td key={c.key} className={cls(c)}>
                    <Skeleton width={j === 0 ? `${70 - (i % 3) * 12}%` : c.align === "right" ? 40 : "60%"} />
                  </td>
                ))}
                {actions ? <td className="dt-actions"><Skeleton width={48} height={28} /></td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : shown.length === 0 ? (
        <div className="dt-empty">{filtering ? "Nothing matches." : (empty ?? "Nothing yet.")}</div>
      ) : (
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={cls(c)}
                    style={c.width ? { width: c.width } : grows.size > 1 && grows.has(c.key) ? { width: `${Math.floor(100 / grows.size)}%` } : undefined}>
                  {c.sort ? (
                    <button type="button" onClick={() => setSort((s) => s?.key === c.key ? { key: c.key, down: !s.down } : { key: c.key, down: false })}>
                      {c.label}{sort?.key === c.key ? (sort.down ? " ↓" : " ↑") : ""}
                    </button>
                  ) : c.label}
                </th>
              ))}
              {actions ? <th className="dt-actions" /> : null}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => {
              const key = rowKey(r);
              return (
                <tr key={key} className={`${onRow ? "open" : ""}${chosen === key ? " chosen" : ""}`}
                    onClick={onRow ? () => onRow(r) : undefined}>
                  {columns.map((c) => (
                    <td key={c.key} className={cls(c)}
                        style={grows.size > 1 && grows.has(c.key) ? { width: `${Math.floor(100 / grows.size)}%` } : undefined}>{c.render(r)}</td>
                  ))}
                  {actions ? <td className="dt-actions" onClick={(e) => e.stopPropagation()}>{actions(r)}</td> : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {pages > 1 ? (
        <div className="dt-pages">
          <Button kind="ghost" disabled={at === 0} onClick={() => setPage(at - 1)}>‹ Previous</Button>
          <span>{at * pageSize + 1}–{Math.min(shown.length, (at + 1) * pageSize)} of {shown.length.toLocaleString()}</span>
          <Button kind="ghost" disabled={at >= pages - 1} onClick={() => setPage(at + 1)}>Next ›</Button>
        </div>
      ) : null}
    </div>
  );
}

function FacetPicker({ label, counts, picked, onChange }: {
  label: string;
  counts: [string, number][];
  picked: Set<string>;
  onChange: (next: Set<string>) => void;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const said = picked.size === 0 ? "all" : picked.size === 1 ? [...picked][0] : `${picked.size} chosen`;
  return (
    <div className="facet" ref={box}>
      <button type="button" className={`btn btn-secondary${picked.size ? " on" : ""}`} onClick={() => setOpen((o) => !o)}>
        {label}: <strong>{said}</strong> ▾
      </button>
      {open ? (
        <div className="menu-list facet-list">
          {counts.map(([value, n]) => (
            <label key={value} className="facet-row">
              <input type="checkbox" checked={picked.has(value)}
                     onChange={(e) => {
                       const next = new Set(picked);
                       if (e.target.checked) next.add(value); else next.delete(value);
                       onChange(next);
                     }} />
              <span>{value}</span>
              <span className="facet-n">{n.toLocaleString()}</span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
