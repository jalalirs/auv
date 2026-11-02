// Where you may dive, and where you will be able to.
//
// Only what you have been granted appears — not filtered here, but simply not
// listed by the platform. An asset nobody granted you is indistinguishable from
// one that does not exist, which is deliberate, and it means this page never
// has to explain an absence.
//
// Under them, the places the platform is for and has not built. Shown as what
// they are — intentions, with what building each takes — so the shape of the
// product is visible before the whole of it exists.

import type { Held, Packages } from "./Deck.js";
import { PlaceCard } from "./Dive.js";
import { Empty } from "./parts.js";
import { useState } from "react";
import type { City, Platform } from "@coral-city/api";
import { Button, Dialog, Menu, Page } from "../ui/components.js";

export function Places({ platform, held, packages, onOpen, onBuild, onStore, onChanged }: {
  platform?: Platform;
  held: Held;
  packages: Packages;
  onOpen: (id: string) => void;
  onBuild?: () => void;
  /** Places iOcean has built, to take one. */
  onStore?: () => void;
  /** Read the places again, after one is retired. */
  onChanged?: () => void | Promise<void>;
}): React.JSX.Element {
  const [trouble, setTrouble] = useState("");
  const [retiring, setRetiring] = useState<City | undefined>();
  const [busy, setBusy] = useState(false);
  const institution = held.institution;
  const yours = held.yourPlaces;

  // Retiring hides a place and refuses new dives in it; its versions, runs
  // and files stay, and the platform can bring it back.
  const retire = async (one: City) => {
    if (!platform) return;
    setBusy(true);
    setTrouble("");
    try {
      await platform.retirePlace(one.id);
      setRetiring(undefined);
      await onChanged?.();
    } catch (problem) {
      setTrouble(problem instanceof Error ? problem.message : "it could not be retired");
      setRetiring(undefined);
    } finally {
      setBusy(false);
    }
  };
  // Only the organisation that owns a place manages it; a place taken from
  // the store is let go of there instead.
  const mayRetire = (one: City) => platform !== undefined && institution !== undefined
    && one.ownedByOrg === institution.id;

  return (
    <Page title="Places" subtitle="Your places. A run pins the version it ran in."
          info="A place is its ground and the objects put on it. Take one iOcean has built from the Store, or compose your own with New place. A run pins the version it ran in, so the reef you dived is the reef anybody can dive again."
          actions={onBuild ? <Button kind="primary" onClick={onBuild}>New place</Button> : undefined}>
      {trouble ? <p className="trouble">{trouble}</p> : null}
      {yours.length === 0 ? (
        <Empty title="No places yet">Compose one with New place, or <a onClick={onStore}>take one from the Store</a>.</Empty>
      ) : (
        <div className="cards">
          {yours.map((one) => (
            <PlaceCard key={one.id} place={one} packages={packages} onOpen={() => onOpen(one.id)}
                       actions={<>
                         <Button onClick={() => onOpen(one.id)}>Open</Button>
                         {mayRetire(one) ? (
                           <Menu label={`More for ${one.name}`}
                                 items={[{ label: "Retire", danger: true, onSelect: () => setRetiring(one) }]} />
                         ) : null}
                       </>} />
          ))}
        </div>
      )}
      {retiring ? (
        <Dialog title={`Retire ${retiring.name}?`} onClose={() => { if (!busy) setRetiring(undefined); }}
                actions={<>
                  <Button kind="ghost" disabled={busy} onClick={() => setRetiring(undefined)}>Cancel</Button>
                  <Button kind="danger" disabled={busy} onClick={() => void retire(retiring)}>{busy ? "Retiring…" : "Retire"}</Button>
                </>}>
          <p>It leaves your places and no new dives can be made in it.</p>
          <p className="note">Its history is kept: every version, run and file stays, and dives already flown in it still replay.</p>
        </Dialog>
      ) : null}
    </Page>
  );
}

