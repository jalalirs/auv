// What can be put in a world, as a modelling tool's asset browser shows it:
// categories down the side, a picture of each thing, search. Click one to
// take it in hand, or drag it into the view.

import React, { useMemo, useState } from "react";

import { CATEGORIES, type Category, type Placeable } from "../platform/scene.js";
import { Icon } from "../ui/icons.js";
import { thumbOf } from "./thumbs.js";

export function AssetBrowser({ items, hand, onHand }: {
  items: Placeable[];
  hand?: string;
  onHand: (key: string | undefined) => void;
}): React.JSX.Element {
  const [category, setCategory] = useState<Category | "All">("All");
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = items.filter((p) => (category === "All" || p.category === category) && (!q || p.name.toLowerCase().includes(q)));
  const counts = useMemo(() => {
    const out = new Map<string, number>();
    for (const p of items) out.set(p.category, (out.get(p.category) ?? 0) + 1);
    return out;
  }, [items]);
  return (
    <div className="ab">
      <nav className="ab-side">
        <button className={category === "All" ? "on" : ""} onClick={() => setCategory("All")}>
          <Icon name="assets" size={15} /><span>All</span><small>{items.length}</small>
        </button>
        {CATEGORIES.map((c) => (
          <button key={c.key} className={category === c.key ? "on" : ""} onClick={() => setCategory(c.key)}>
            <Icon name={c.icon} size={15} /><span>{c.key}</span><small>{counts.get(c.key) ?? 0}</small>
          </button>
        ))}
      </nav>
      <div className="ab-main">
        <header>
          <label className="ol-search">
            <Icon name="search" size={14} />
            <input placeholder="Search assets" value={query} onChange={(e) => setQuery(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); e.stopPropagation(); }} />
          </label>
          <span className="ab-says">{hand ? items.find((p) => p.key === hand)?.says : "click to take one in hand, or drag it into the view"}</span>
        </header>
        <div className="ab-tiles">
          {shown.length === 0 ? <em>{category === "Your objects" ? "no objects of yours are ready" : "nothing matches"}</em> : null}
          {shown.map((p) => <Tile key={p.key} p={p} on={hand === p.key} onClick={() => onHand(hand === p.key ? undefined : p.key)} />)}
        </div>
      </div>
    </div>
  );
}

function Tile({ p, on, onClick }: { p: Placeable; on: boolean; onClick: () => void }): React.JSX.Element {
  const picture = useMemo(() => p.asset ? undefined : thumbOf(p.kind === "coral" ? `coral:${p.form}` : p.kind), [p]);
  return (
    <button className={`ab-tile${on ? " on" : ""}`} onClick={onClick} title={`${p.name}: ${p.says}`} draggable
            onDragStart={(e) => { e.dataTransfer.setData("application/x-iocean", p.key); e.dataTransfer.effectAllowed = "copy"; }}>
      <span className="ab-pic">
        {picture ? <img src={picture} alt="" draggable={false} /> : <Icon name={p.icon} size={34} />}
        <span className="ab-badge"><Icon name={p.icon} size={12} /></span>
      </span>
      <span className="ab-name">{p.name}</span>
    </button>
  );
}
