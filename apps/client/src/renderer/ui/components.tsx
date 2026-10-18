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

export function Page({ title, subtitle, info, crumb, onCrumb, actions, tabs, tab, onTab, toolbar, wide, children }: {
  title: React.ReactNode;
  /** One line. Anything longer goes in `info`. */
  subtitle?: React.ReactNode;
  info?: React.ReactNode;
  /** Where Back goes, by name. */
  crumb?: string;
  onCrumb?: () => void;
  actions?: React.ReactNode;
  tabs?: Tab[];
  tab?: string;
  onTab?: (key: string) => void;
  toolbar?: React.ReactNode;
  /** Full width; otherwise the body is held to a readable measure. */
  wide?: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="page">
      <header className="page-top">
        {crumb ? <button type="button" className="crumb" onClick={onCrumb}>‹ {crumb}</button> : null}
        <div className="page-title-row">
          <div className="page-titles">
            <h1>{title}{info ? <Info>{info}</Info> : null}</h1>
            {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="page-actions">{actions}</div> : null}
        </div>
        {tabs ? (
          <nav className="tabs" role="tablist">
            {tabs.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={t.key === tab}
                      onClick={() => onTab?.(t.key)}>
                {t.label}{t.count !== undefined ? <span className="tab-count">{t.count.toLocaleString()}</span> : null}
              </button>
            ))}
          </nav>
        ) : null}
        {toolbar ? <div className="toolbar">{toolbar}</div> : null}
      </header>
      <div className={`page-body${wide ? " wide" : ""}`}>{children}</div>
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

export function Dialog({ title, onClose, actions, children }: {
  title: string;
  onClose: () => void;
  actions?: React.ReactNode;
  children: React.ReactNode;
}): React.JSX.Element {
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  return (
    <div className="dialog-shade" onMouseDown={onClose}>
      <div className="dialog" role="dialog" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
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
};

export type Facet<T> = { key: string; label: string; value: (row: T) => string | undefined };

export function Table<T>({ rows, columns, rowKey, onRow, search, searchLabel = "Search", facets = [], actions,
                           pageSize = 25, empty, initialSort, chosen }: {
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
}): React.JSX.Element {
  const [words, setWords] = useState("");
  const [picked, setPicked] = useState<Record<string, Set<string>>>({});
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

  return (
    <div className="dt">
      {search || facets.length ? (
        <div className="dt-tools">
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
          <span className="dt-count">{filtering ? `${shown.length.toLocaleString()} of ${rows.length.toLocaleString()}` : rows.length.toLocaleString()}</span>
        </div>
      ) : null}
      {shown.length === 0 ? (
        <div className="dt-empty">{filtering ? "Nothing matches." : (empty ?? "Nothing yet.")}</div>
      ) : (
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`${c.align === "right" ? "right " : ""}p${c.priority ?? 1}`}
                    style={c.width ? { width: c.width } : undefined}>
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
                    <td key={c.key} className={`${c.align === "right" ? "right " : ""}p${c.priority ?? 1}`}>{c.render(r)}</td>
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
