// A controller deployed from its source: a public GitHub repository, a zip,
// or the command line as before (plan item 69).
//
// The platform clones or unpacks the source, finds the controller, checks it
// can fly the vehicle it was written for and runs it in the SDK's tank, puts
// it on the ROS 2 base and registers it as a build of that controller. Each
// build says what it did, step by step; a GitHub one can be built again from
// the newest commit (Pull latest).

import { useEffect, useRef, useState } from "react";
import type { ControllerBuild, ControllerBuildBrief, Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { ago } from "./parts.js";
import { Button, Dialog, Status, Table, type Tone } from "../ui/components.js";

type One = {
  ok?: boolean; controller?: string; vehicle?: string; slug?: string; name?: string; failure?: string; stackId?: string;
  checks?: { vehicle?: { ok?: boolean; problems?: string[] }; tank?: { ok?: boolean; said?: string; score?: number | null } };
  sizeBytes?: number; imageDigest?: string;
};
type Report = {
  ok?: boolean; controller?: string; vehicle?: string; slug?: string; name?: string; failure?: string;
  controllers?: One[];
  source?: { kind?: string; url?: string; ref?: string; commit?: string; path?: string; name?: string };
  checks?: { vehicle?: { ok?: boolean; problems?: string[] }; tank?: { ok?: boolean; said?: string; score?: number | null } };
  sizeBytes?: number; imageDigest?: string;
};

export function stateTone(b: ControllerBuild): Tone {
  return b.state === "ready" ? "good" : b.state === "failed" ? "bad" : "busy";
}

export function sourceSaid(b: ControllerBuild): string {
  const s = b.brief.source as { kind: string; url?: string; ref?: string; path?: string; name?: string };
  const commit = (b.report as Report | undefined)?.source?.commit;
  if (s.kind === "git") {
    const repo = (s.url ?? "").replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "");
    return `${repo}${s.ref ? ` @ ${s.ref}` : ""}${s.path ? ` / ${s.path}` : ""}${commit ? ` (${commit.slice(0, 7)})` : ""}`;
  }
  return s.name ?? "a zip";
}

/** Deploy one: from GitHub, from a zip, or from the command line. */
export function DeployDialog({ platform, held, onClose, onStarted }: {
  platform: Platform;
  held: Held;
  onClose: () => void;
  onStarted: (build: ControllerBuild) => void;
}): React.JSX.Element {
  const [how, setHow] = useState<"git" | "zip" | "cli">("git");
  const [advanced, setAdvanced] = useState(false);
  const [found, setFound] = useState<{ slug: string; name?: string; entry?: string }[] | undefined>();
  const [lookSaid, setLookSaid] = useState("");
  const [ticked, setTicked] = useState<string[]>([]);
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [path, setPath] = useState("");
  const [file, setFile] = useState<File | undefined>();
  const [controller, setController] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState<string | undefined>();
  const [trouble, setTrouble] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const institution = held.institution;
  const github = /^https:\/\/github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+?(\.git)?\/?$/.test(url.trim());
  // What the repository holds, looked up once its address reads right.
  useEffect(() => {
    setFound(undefined);
    setLookSaid("");
    if (how !== "git" || !github) return;
    let stale = false;
    const later = setTimeout(() => {
      platform.lookControllerSource(url.trim(), ref.trim() || undefined, path.trim() || undefined)
        .then((said) => {
          if (stale) return;
          setFound(said.controllers);
          setTicked(said.controllers.map((c) => c.slug));
          setLookSaid(said.said ?? "");
        })
        .catch((problem) => { if (!stale) setLookSaid(problem instanceof Error ? problem.message : "could not look at it"); });
    }, 500);
    return () => { stale = true; clearTimeout(later); };
  }, [platform, how, github, url, ref, path]);
  const ready = !!institution && !sent && (how === "git" ? github && (!found?.length || ticked.length > 0)
    : how === "zip" ? !!file && /\.zip$/i.test(file.name) : false);

  const start = async () => {
    if (!institution) return;
    setTrouble("");
    try {
      let source: ControllerBuildBrief["source"];
      if (how === "git") {
        source = { kind: "git", url: url.trim(), ...(ref.trim() ? { ref: ref.trim() } : {}), ...(path.trim() ? { path: path.trim() } : {}) };
      } else {
        setSent("hashing");
        const stored = await platform.upload(institution.id, file!, { onProgress: (stage) => setSent(stage) });
        source = { kind: "zip", objectId: stored.id, name: file!.name };
      }
      setSent("starting");
      const several = how === "git" && found && found.length > 0;
      const build = await platform.startControllerBuild(institution.id, {
        source,
        ...(several && ticked.length < found!.length ? { controllers: ticked } : {}),
        ...(!several && controller.trim() ? { controller: controller.trim() } : {}),
        ...(!several && name.trim() ? { name: name.trim() } : {}),
      });
      onStarted(build);
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "the build could not start");
      setSent(undefined);
    }
  };

  return (
    <Dialog title="Deploy a controller" onClose={onClose}
            actions={how === "cli" ? <Button kind="primary" onClick={onClose}>Done</Button> : (
              <><Button kind="ghost" onClick={onClose}>Cancel</Button>
                <Button kind="primary" disabled={!ready} onClick={() => void start()}>{sent ? `${sent}…` : "Build and deploy"}</Button></>
            )}>
      <div className="segmented">
        <button type="button" aria-pressed={how === "git"} onClick={() => setHow("git")}>From GitHub</button>
        <button type="button" aria-pressed={how === "zip"} onClick={() => setHow("zip")}>From a zip</button>
        <button type="button" aria-pressed={how === "cli"} onClick={() => setHow("cli")}>Command line</button>
      </div>
      {how === "git" ? (
        <>
          <label className="field"><span>Repository</span>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo" autoFocus />
          </label>
          {url.trim() && !github ? <p className="trouble">A public GitHub repository: https://github.com/owner/repo.</p> : null}
          <button type="button" className="disclose" onClick={() => setAdvanced((a) => !a)}>{advanced ? "▾" : "▸"} Advanced: a branch other than its default, or a folder in it</button>
          {advanced ? (
            <div className="field-row">
              <label className="field"><span>Branch, tag or commit</span>
                <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="its default branch" />
              </label>
              <label className="field"><span>Folder</span>
                <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="the repository's root" />
              </label>
            </div>
          ) : null}
          {github && found === undefined && !lookSaid ? <p className="note">Looking at the repository…</p> : null}
          {found && found.length > 0 ? (
            <div className="field"><span>{found.length} controller{found.length === 1 ? "" : "s"} in it</span>
              <div className="choices">
                {found.map((c) => {
                  const on = ticked.includes(c.slug);
                  return (
                    <label key={c.slug} className="check found">
                      <input type="checkbox" checked={on}
                             onChange={() => setTicked((was) => on ? was.filter((x) => x !== c.slug) : [...was, c.slug])} />
                      <span><strong>{c.name ?? c.slug}</strong> <span className="note">{c.entry ?? c.slug}</span></span>
                    </label>
                  );
                })}
              </div>
            </div>
          ) : lookSaid ? <p className="note">{lookSaid}</p> : null}
        </>
      ) : how === "zip" ? (
        <>
          <input ref={picker} type="file" accept=".zip" hidden onChange={(e) => { setFile(e.target.files?.[0]); e.target.value = ""; }} />
          <Button onClick={() => picker.current?.click()}>{file ? file.name : "Choose a zip of the controller's folder"}</Button>
        </>
      ) : null}
      {how === "cli" ? (
        <ol className="steps">
          <li><code>pip install -e packages/sdk-python</code></li>
          <li>Write a class against <code>iocean.Controller</code>; try it with <code>iocean tank</code>.</li>
          <li><code>iocean deploy your.py --slug name</code></li>
        </ol>
      ) : (
        <>
          {how === "git" && found && found.length > 0 ? null : <div className="field-row">
            <label className="field"><span>Controller</span>
              <input value={controller} onChange={(e) => setController(e.target.value)} placeholder="found by itself; or file.py:Class" />
            </label>
            <label className="field"><span>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="from iocean.toml or the class" />
            </label>
          </div>}
          <p className="note">The platform builds every controller the repository&rsquo;s <code>iocean.toml</code> lists (or each <code>controllers/&lt;name&gt;/controller.py</code>, or the one class built on <code>iocean.Controller</code>): it installs its <code>requirements.txt</code>, checks it can fly its vehicle, runs it 20 s in the SDK&rsquo;s tank, and registers it. A controller that is a model says what it needs in <code>iocean.toml</code> (<code>[needs] gpu_memory = "8G"</code>).</p>
        </>
      )}
      {trouble ? <p className="trouble">{trouble}</p> : null}
    </Dialog>
  );
}

/** Every build, newest first, each with its steps and what its checks said. */
export function Builds({ platform, held, onRefresh }: {
  platform: Platform;
  held: Held;
  onRefresh?: () => void;
}): React.JSX.Element {
  const [builds, setBuilds] = useState<ControllerBuild[] | undefined>();
  const [open, setOpen] = useState<ControllerBuild | undefined>();
  const institution = held.institution;

  useEffect(() => {
    if (!institution) return;
    let stale = false;
    const read = () => platform.controllerBuildsOf(institution.id)
      .then((found) => {
        if (stale) return;
        setBuilds((was) => {
          if (was && found.some((b) => b.state === "ready" && was.find((w) => w.id === b.id)?.state !== "ready")) onRefresh?.();
          return found;
        });
      }).catch(() => setBuilds([]));
    void read();
    const again = setInterval(() => void read(), 5000);
    return () => { stale = true; clearInterval(again); };
  }, [platform, institution, onRefresh]);

  const again = async (b: ControllerBuild) => {
    const made = await platform.controllerBuildAgain(b.id);
    setBuilds((was) => [made, ...(was ?? [])]);
  };

  return (
    <>
      <Table rows={builds ?? []} rowKey={(b) => b.id} onRow={setOpen}
             search={(b) => `${b.slug} ${sourceSaid(b)}`} searchLabel="Search builds"
             facets={[{ key: "state", label: "State", value: (b) => b.state },
                      { key: "from", label: "From", value: (b) => (b.brief.source as { kind: string }).kind === "git" ? "GitHub" : "zip" }]}
             initialSort={{ key: "when", down: true }}
             empty={builds === undefined ? "Reading…" : "No builds yet. Deploy one from GitHub or a zip."}
             columns={[
               { key: "controller", label: "Controller", grow: true, sort: (a, b) => a.slug.localeCompare(b.slug),
                 render: (b) => {
                   const r = b.report as Report | undefined;
                   const many = r?.controllers;
                   const title = many && many.length > 1
                     ? `${b.slug}: ${many.filter((c) => c.ok).length} of ${many.length} controllers`
                     : many?.[0]?.name ?? r?.name ?? b.slug;
                   return <><span className="cell-main">{title}</span><span className="cell-sub">{sourceSaid(b)}</span></>;
                 } },
               { key: "doing", label: "What it said", priority: 2, grow: true,
                 render: (b) => <span className="cell-sub">{b.state === "failed" ? (b.failure ?? (b.report as Report | undefined)?.failure) : b.steps[b.steps.length - 1]?.say ?? "waiting for a machine"}</span> },
               { key: "when", label: "When", priority: 3, sort: (a, b) => a.createdAt.localeCompare(b.createdAt),
                 render: (b) => <span className="cell-meta">{ago(b.createdAt)}</span> },
               { key: "state", label: "State", render: (b) => <Status tone={stateTone(b)}>{b.state}</Status> },
             ]}
             actions={(b) => (b.brief.source as { kind: string }).kind === "git" && b.state !== "running" && b.state !== "queued"
               ? <Button onClick={() => void again(b)}>Pull latest</Button> : null} />
      {open ? <BuildDialog build={open} onClose={() => setOpen(undefined)} /> : null}
    </>
  );
}

function BuildDialog({ build, onClose }: { build: ControllerBuild; onClose: () => void }): React.JSX.Element {
  const r = (build.report ?? {}) as Report;
  const each: One[] = r.controllers ?? (r.controller ? [r as One] : []);
  return (
    <Dialog title={build.slug} onClose={onClose} actions={<Button kind="primary" onClick={onClose}>Close</Button>}>
      <p className="note">{sourceSaid(build)} · <Status tone={stateTone(build)}>{build.state}</Status></p>
      {each.length > 0 ? (
        <table className="dialog-table">
          <thead><tr><th>Controller</th><th>Vehicle</th><th>Tank</th><th /></tr></thead>
          <tbody>
            {each.map((c, i) => (
              <tr key={c.slug ?? i}>
                <td><strong>{c.name ?? c.slug}</strong><br /><span className="cell-meta">{c.controller}</span></td>
                <td className="cell-meta">{c.vehicle}{c.checks?.vehicle && !c.checks.vehicle.ok ? `: ${(c.checks.vehicle.problems ?? []).join("; ")}` : ""}</td>
                <td className="cell-meta">{c.checks?.tank?.said ?? "—"}</td>
                <td><Status tone={c.ok ? "good" : "bad"}>{c.ok ? "built" : "refused"}</Status></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {each.filter((c) => !c.ok && c.failure).map((c) => <p key={c.slug} className="trouble">{c.slug}: {c.failure}</p>)}
      {build.state === "failed" && each.length === 0 ? <p className="trouble">{build.failure ?? r.failure}</p> : null}
      <ol className="builder-steps">
        {build.steps.map((s, i) => <li key={i}>{s.say}</li>)}
      </ol>
    </Dialog>
  );
}
