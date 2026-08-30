import { useState } from "react";

import { api, Refused } from "../api/client.js";
import type { Binding, Principal } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";

/**
 * People, institutions, and what each has been granted.
 *
 * A grant attaches a role to a subject at a scope, and binding an institution
 * grants the role to every one of its members. That is the whole of it: there
 * is one kind of grant, and a place, a vehicle and a queue are granted the same
 * way, so there is one thing to understand rather than three.
 */
export function Access() {
  const [version, setVersion] = useState(0);
  const again = () => setVersion((n) => n + 1);

  const organisations = useAsked(() => api.organisations(), [version]);
  const people = useAsked(() => api.people(), [version]);

  return (
    <>
      <h2>People and institutions</h2>
      <p className="lede">
        Everyone who can act, and the institutions they belong to. Granting an
        institution a place, a vehicle or a queue grants it to every member, so
        access is usually given here once rather than to each person in turn.
      </p>

      <NewPerson onDone={again} />
      <NewInstitution onDone={again} />

      <h3>Institutions</h3>
      <Answered
        asked={organisations}
        empty={{
          of: (value) => value.organisations.length === 0,
          say: "There are no institutions. The first was founded when this installation was bootstrapped, so an empty list here means something is wrong.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead><tr><th>Handle</th><th>Name</th><th>Identifier</th><th>Founded</th></tr></thead>
              <tbody>
                {value.organisations.map((org) => (
                  <tr key={org.id}>
                    <td className="mono">{org.slug}</td>
                    <td>{org.name}</td>
                    <td className="mono">{org.id}</td>
                    <td><When value={org.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      <h3>People</h3>
      <Answered
        asked={people}
        empty={{ of: (value) => value.people.length === 0, say: "Nobody can act on this installation." }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Name</th><th>Address</th><th>Kind</th><th>State</th><th>Identifier</th></tr>
              </thead>
              <tbody>
                {value.people.map((person) => (
                  <tr key={person.id}>
                    <td>{person.displayName}</td>
                    <td className="mono">{person.email || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    <td>{person.kind}</td>
                    <td>
                      {person.disabled
                        ? <Tag kind="idle">disabled</Tag>
                        : <Tag kind="good">active</Tag>}
                    </td>
                    <td className="mono">{person.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>
    </>
  );
}

function NewPerson({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [said, setSaid] = useState<string | null>(null);

  if (!open) {
    return <p><button className="quiet" onClick={() => setOpen(true)}>Add someone</button></p>;
  }

  return (
    <form
      className="card" style={{ maxWidth: "30rem", marginBottom: "1rem" }}
      onSubmit={(event) => {
        event.preventDefault();
        setSaid(null);
        api.createPerson(name, email, secret)
          .then(() => { setOpen(false); setName(""); setEmail(""); setSecret(""); onDone(); })
          .catch((error: unknown) =>
            setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
      }}
    >
      <div className="label" style={{ marginBottom: "0.6rem" }}>Someone who can sign in</div>
      <label htmlFor="p-name">Name</label>
      <input id="p-name" required value={name} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="p-email">Address</label>
      <input id="p-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="p-secret">Secret</label>
      <input
        id="p-secret" type="password" required minLength={16}
        value={secret} onChange={(e) => setSecret(e.target.value)}
      />
      <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginTop: "-0.6rem" }}>
        Chosen here and shown to nobody afterwards, so give it to them by another route.
      </p>
      {said && <p className="refused" style={{ marginBottom: "0.8rem" }}>{said}</p>}
      <button type="submit">Add</button>{" "}
      <button type="button" className="quiet" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}

function NewInstitution({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [said, setSaid] = useState<string | null>(null);

  if (!open) {
    return (
      <p style={{ marginTop: "-0.6rem", marginBottom: "1.4rem" }}>
        <button className="quiet" onClick={() => setOpen(true)}>Found an institution</button>
      </p>
    );
  }

  return (
    <form
      className="card" style={{ maxWidth: "30rem", marginBottom: "1.4rem" }}
      onSubmit={(event) => {
        event.preventDefault();
        setSaid(null);
        api.createOrganisation(slug, name)
          .then(() => { setOpen(false); setSlug(""); setName(""); onDone(); })
          .catch((error: unknown) =>
            setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
      }}
    >
      <div className="label" style={{ marginBottom: "0.6rem" }}>An institution</div>
      <label htmlFor="o-slug">Handle</label>
      <input
        id="o-slug" required pattern="[a-z0-9][a-z0-9-]*[a-z0-9]"
        value={slug} onChange={(e) => setSlug(e.target.value)}
      />
      <label htmlFor="o-name">Name</label>
      <input id="o-name" required value={name} onChange={(e) => setName(e.target.value)} />
      {said && <p className="refused" style={{ marginBottom: "0.8rem" }}>{said}</p>}
      <button type="submit">Found</button>{" "}
      <button type="button" className="quiet" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}

/**
 * Grant and withdraw access to one place, vehicle or queue.
 *
 * Shown beside whatever it governs rather than on a screen of its own, because
 * "who may use this" is a question about the thing, not a separate subject.
 */
export function Grants({
  assetId, grants, grant, revoke, noun,
}: {
  assetId: string;
  grants: () => Promise<{ grants: Binding[] }>;
  grant: (subjectKind: string, subjectId: string, role: string) => Promise<Binding>;
  revoke: (bindingId: string) => Promise<void>;
  noun: string;
}) {
  const [version, setVersion] = useState(0);
  const again = () => setVersion((n) => n + 1);

  const held = useAsked(grants, [assetId, version]);
  const organisations = useAsked(() => api.organisations(), [version]);
  const people = useAsked(() => api.people(), [version]);

  const [subject, setSubject] = useState("");
  const [role, setRole] = useState("viewer");
  const [said, setSaid] = useState<string | null>(null);

  const subjects: { id: string; label: string; kind: string }[] = [
    ...(organisations.state === "answered"
      ? organisations.value.organisations.map((org) => (
        { id: org.id, label: `${org.name} (institution)`, kind: "org" }))
      : []),
    ...(people.state === "answered"
      ? people.value.people.filter((person) => !person.disabled).map((person: Principal) => (
        { id: person.id, label: `${person.displayName} (person)`, kind: "principal" }))
      : []),
  ];

  return (
    <>
      <h3>Who may use this {noun}</h3>
      <Answered
        asked={held}
        empty={{
          of: (value) => value.grants.length === 0,
          say: `Nobody holds a grant on this ${noun}, so only those with authority at the platform can see or use it.`,
        }}
      >
        {(value) => (
          <div className="scroll" style={{ marginBottom: "0.9rem" }}>
            <table>
              <thead><tr><th>Subject</th><th>Kind</th><th>Role</th><th>Granted</th><th /></tr></thead>
              <tbody>
                {value.grants.map((binding) => (
                  <tr key={binding.id}>
                    <td className="mono">{nameOf(binding.subjectId, subjects)}</td>
                    <td>{binding.subjectKind}</td>
                    <td><Tag kind="accent">{binding.role}</Tag></td>
                    <td><When value={binding.createdAt} /></td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="quiet"
                        onClick={() => {
                          setSaid(null);
                          revoke(binding.id).then(again).catch((error: unknown) =>
                            setSaid(error instanceof Refused ? error.message : "Could not withdraw it."));
                        }}
                      >
                        Withdraw
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      <form
        style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end", flexWrap: "wrap" }}
        onSubmit={(event) => {
          event.preventDefault();
          const chosen = subjects.find((entry) => entry.id === subject);
          if (!chosen) return;
          setSaid(null);
          grant(chosen.kind, chosen.id, role)
            .then(() => { setSubject(""); again(); })
            .catch((error: unknown) =>
              setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
        }}
      >
        <span>
          <label htmlFor={`subject-${assetId}`}>Grant to</label>
          <select
            id={`subject-${assetId}`} required value={subject}
            onChange={(event) => setSubject(event.target.value)}
            style={{ padding: "0.42rem", font: "inherit", minWidth: "16rem" }}
          >
            <option value="">choose…</option>
            {subjects.map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.label}</option>
            ))}
          </select>
        </span>
        <span>
          <label htmlFor={`role-${assetId}`}>As</label>
          <select
            id={`role-${assetId}`} value={role}
            onChange={(event) => setRole(event.target.value)}
            style={{ padding: "0.42rem", font: "inherit" }}
          >
            <option value="viewer">viewer</option>
            <option value="contributor">contributor</option>
            <option value="steward">steward</option>
            <option value="admin">admin</option>
          </select>
        </span>
        <button type="submit" disabled={subject === ""}>Grant</button>
      </form>
      {said && <p className="refused" style={{ marginTop: "0.8rem" }}>{said}</p>}
    </>
  );
}

function nameOf(id: string, subjects: { id: string; label: string }[]): string {
  return subjects.find((entry) => entry.id === id)?.label ?? id;
}
