// The scene tree: everything in a world as a row, the way a modelling tool's
// outliner lists it. Click to choose, Shift for a run, Ctrl or Cmd for one
// more; the eye hides it, the lock keeps it where it is; double-click frames
// it; right-click for the rest.

import React, { useMemo, useState } from "react";

import { flat, type Node } from "../platform/scene.js";
import { Icon } from "../ui/icons.js";

export function Outliner({ nodes, selected, open, onOpen, onSelect, onToggle, onFrame, onMenu, renaming, onRename }: {
  nodes: Node[];
  selected: string[];
  open: Set<string>;
  onOpen: (id: string, open: boolean) => void;
  onSelect: (ids: string[], how: "replace" | "add" | "toggle") => void;
  onToggle: (node: Node, what: "hidden" | "locked") => void;
  onFrame: (node: Node) => void;
  onMenu: (node: Node, at: { x: number; y: number }) => void;
  renaming?: string;
  onRename: (id: string, name: string | undefined) => void;
}): React.JSX.Element {
  const [query, setQuery] = useState("");
  const [anchor, setAnchor] = useState<string | undefined>();
  const chosen = useMemo(() => new Set(selected), [selected]);
  const q = query.trim().toLowerCase();

  // Searching shows what matches and the branches it is on.
  const keep = useMemo(() => {
    if (!q) return undefined;
    const kept = new Set<string>();
    const walk = (n: Node): boolean => {
      const below = (n.children ?? []).map(walk).some(Boolean);
      const hit = n.name.toLowerCase().includes(q) || (n.note ?? "").toLowerCase().includes(q);
      if (hit || below) kept.add(n.id);
      return hit || below;
    };
    nodes.forEach(walk);
    return kept;
  }, [nodes, q]);

  // The rows as they stand, for a Shift run.
  const rows = useMemo(() => {
    const out: Node[] = [];
    const walk = (n: Node) => {
      if (keep && !keep.has(n.id)) return;
      out.push(n);
      if (n.children && (keep || open.has(n.id))) n.children.forEach(walk);
    };
    nodes.forEach(walk);
    return out;
  }, [nodes, open, keep]);

  const choose = (n: Node, e: React.MouseEvent) => {
    // A group of items stands for its items.
    const of = (x: Node) => x.children?.length && !x.item ? [x.id, ...flat(x.children).filter((c) => c.item).map((c) => c.id)] : [x.id];
    if (e.shiftKey && anchor) {
      const a = rows.findIndex((r) => r.id === anchor), b = rows.findIndex((r) => r.id === n.id);
      if (a >= 0 && b >= 0) {
        onSelect(rows.slice(Math.min(a, b), Math.max(a, b) + 1).filter((r) => r.item).map((r) => r.id), "add");
        return;
      }
    }
    setAnchor(n.id);
    onSelect(of(n), e.metaKey || e.ctrlKey ? "toggle" : "replace");
  };

  const row = (n: Node, depth: number): React.ReactNode => {
    if (keep && !keep.has(n.id)) return null;
    const kids = n.children ?? [];
    const expanded = !!keep || open.has(n.id);
    return (
      <React.Fragment key={n.id}>
        <div className={`ol-row${chosen.has(n.id) ? " on" : ""}${n.hidden ? " hidden" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}
             onClick={(e) => choose(n, e)} onDoubleClick={() => onFrame(n)}
             onContextMenu={(e) => { e.preventDefault(); if (!chosen.has(n.id)) choose(n, e); onMenu(n, { x: e.clientX, y: e.clientY }); }}
             title={n.note ? `${n.name}, ${n.note}` : n.name}>
          <button className={`ol-caret${kids.length ? "" : " none"}${expanded ? " open" : ""}`} tabIndex={-1}
                  onClick={(e) => { e.stopPropagation(); if (kids.length) onOpen(n.id, !expanded); }}>
            {kids.length ? <Icon name="chevron" size={12} /> : null}
          </button>
          <span className="ol-icon"><Icon name={n.icon} size={15} /></span>
          {renaming === n.id ? (
            <input className="ol-rename" autoFocus defaultValue={n.name} onClick={(e) => e.stopPropagation()}
                   onBlur={(e) => onRename(n.id, e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") onRename(n.id, e.currentTarget.value); if (e.key === "Escape") onRename(n.id, undefined); e.stopPropagation(); }} />
          ) : <span className="ol-name">{n.name}</span>}
          {n.note ? <small className="ol-note">{n.note}</small> : null}
          {n.toggles ? (
            <span className="ol-toggles">
              {n.item ? (
                <button className={n.locked ? "on" : ""} title={n.locked ? "Unlock" : "Lock"} tabIndex={-1}
                        onClick={(e) => { e.stopPropagation(); onToggle(n, "locked"); }}>
                  <Icon name={n.locked ? "lock" : "unlock"} size={13} />
                </button>
              ) : null}
              <button className={n.hidden ? "on" : ""} title={n.hidden ? "Show" : "Hide"} tabIndex={-1}
                      onClick={(e) => { e.stopPropagation(); onToggle(n, "hidden"); }}>
                <Icon name={n.hidden ? "eyeOff" : "eye"} size={13} />
              </button>
            </span>
          ) : null}
        </div>
        {expanded ? kids.map((k) => row(k, depth + 1)) : null}
      </React.Fragment>
    );
  };

  return (
    <div className="ol">
      <label className="ol-search">
        <Icon name="search" size={14} />
        <input placeholder="Search the scene" value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); e.stopPropagation(); }} />
      </label>
      <div className="ol-rows" role="tree">{nodes.map((n) => row(n, 0))}</div>
    </div>
  );
}
