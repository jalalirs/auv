// The pieces every page shares.

import { useEffect, useState } from "react";

import mark from "../../../assets/coral-city.svg";

/**
 * A picture's address, once the picture behind it has actually loaded.
 *
 * A background that is set to a new address shows nothing until the bytes
 * arrive. When the address changes — a package re-read with fresh signatures,
 * or a different place chosen — the old picture stays until the new one is
 * ready, so the banner never blinks to black between them.
 */
export function useLoadedPicture(url: string | undefined): string | undefined {
  const [shown, setShown] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (url === undefined) { setShown(undefined); return; }
    let live = true;
    const image = new Image();
    image.onload = () => { if (live) setShown(url); };
    image.src = url;
    return () => { live = false; };
  }, [url]);
  return shown;
}

export function Badge({ under }: { under?: string }): React.JSX.Element {
  return (
    <div className="badge">
      <img src={mark} alt="" />
      <div>
        <h1>Coral City</h1>
        {under === undefined ? null : <p>{under}</p>}
      </div>
    </div>
  );
}

export function Fact({ of, is, note }: { of: string; is: string; note?: string }): React.JSX.Element {
  return (
    <div className="fact" title={note}>
      <span>{of}</span>
      <strong>{is}</strong>
    </div>
  );
}

export function Pill({ kind, children, title }: {
  kind?: "good" | "busy" | "bad";
  children: React.ReactNode;
  title?: string;
}): React.JSX.Element {
  return <span className={kind ? `pill ${kind}` : "pill"} title={title}>{children}</span>;
}

/**
 * A place where something will be and is not.
 *
 * Said plainly, with what it will be and why it is not here yet. An empty panel
 * that explains itself is honest; one that shows invented content so the screen
 * looks finished is not, and it is the more tempting of the two.
 */
export function Empty({ title, children, soon }: {
  title: string;
  children: React.ReactNode;
  soon?: string;
}): React.JSX.Element {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <p>{children}</p>
      {soon === undefined ? null : <span className="soon">{soon}</span>}
    </div>
  );
}

export function PageHead({ title, says, back, onBack, aside }: {
  title: string;
  says?: string;
  back?: string;
  onBack?: () => void;
  aside?: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="page-head">
      {back === undefined ? null : (
        <a className="back" onClick={onBack}>← {back}</a>
      )}
      <div className="page-head-row">
        <div>
          <h1>{title}</h1>
          {says === undefined ? null : <p>{says}</p>}
        </div>
        {aside}
      </div>
    </div>
  );
}

/** A key and a value, in a table of them. */
export function Row({ of, is, note }: { of: string; is: React.ReactNode; note?: string }): React.JSX.Element {
  return (
    <div className="kv" title={note}>
      <span>{of}</span>
      <strong>{is}</strong>
    </div>
  );
}

/** How long ago, in words somebody would use. */
export function ago(when: string | undefined): string {
  if (when === undefined) return "";
  const seconds = Math.max(0, (Date.now() - Date.parse(when)) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

/** A number with the precision a reader wants, and no more. */
export function fixed(value: number | undefined, digits = 1, unit = ""): string {
  if (value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}${unit}`;
}

/** Who a picture is by, in one small line under it, when it is somebody's photograph. */
export function Credit({ of }: { of: { title?: string; author?: string; licence?: string; source?: string; kind?: string } | undefined }): React.JSX.Element | null {
  if (of === undefined) return null;
  if (of.kind === "render") return <p className="credit">Rendered from the package's own model.</p>;
  const words = [of.author ? `Photograph by ${of.author}` : "Photograph", of.licence].filter(Boolean).join(", ");
  return (
    <p className="credit">
      {of.source ? <a href={of.source} target="_blank" rel="noreferrer">{words}</a> : words}
    </p>
  );
}
