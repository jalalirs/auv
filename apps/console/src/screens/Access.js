import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { api, Refused } from "../api/client.js";
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
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "People and institutions" }), _jsx("p", { className: "lede", children: "Everyone who can act, and the institutions they belong to. Granting an institution a place, a vehicle or a queue grants it to every member, so access is usually given here once rather than to each person in turn." }), _jsx(NewPerson, { onDone: again }), _jsx(NewInstitution, { onDone: again }), _jsx("h3", { children: "Institutions" }), _jsx(Answered, { asked: organisations, empty: {
                    of: (value) => value.organisations.length === 0,
                    say: "There are no institutions. The first was founded when this installation was bootstrapped, so an empty list here means something is wrong.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Handle" }), _jsx("th", { children: "Name" }), _jsx("th", { children: "Identifier" }), _jsx("th", { children: "Founded" })] }) }), _jsx("tbody", { children: value.organisations.map((org) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: org.slug }), _jsx("td", { children: org.name }), _jsx("td", { className: "mono", children: org.id }), _jsx("td", { children: _jsx(When, { value: org.createdAt }) })] }, org.id))) })] }) })) }), _jsx("h3", { children: "People" }), _jsx(Answered, { asked: people, empty: { of: (value) => value.people.length === 0, say: "Nobody can act on this installation." }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Name" }), _jsx("th", { children: "Address" }), _jsx("th", { children: "Kind" }), _jsx("th", { children: "State" }), _jsx("th", { children: "Identifier" })] }) }), _jsx("tbody", { children: value.people.map((person) => (_jsxs("tr", { children: [_jsx("td", { children: person.displayName }), _jsx("td", { className: "mono", children: person.email || _jsx("span", { style: { color: "var(--muted)" }, children: "\u2014" }) }), _jsx("td", { children: person.kind }), _jsx("td", { children: person.disabled
                                                ? _jsx(Tag, { kind: "idle", children: "disabled" })
                                                : _jsx(Tag, { kind: "good", children: "active" }) }), _jsx("td", { className: "mono", children: person.id })] }, person.id))) })] }) })) })] }));
}
function NewPerson({ onDone }) {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [secret, setSecret] = useState("");
    const [said, setSaid] = useState(null);
    if (!open) {
        return _jsx("p", { children: _jsx("button", { className: "quiet", onClick: () => setOpen(true), children: "Add someone" }) });
    }
    return (_jsxs("form", { className: "card", style: { maxWidth: "30rem", marginBottom: "1rem" }, onSubmit: (event) => {
            event.preventDefault();
            setSaid(null);
            api.createPerson(name, email, secret)
                .then(() => { setOpen(false); setName(""); setEmail(""); setSecret(""); onDone(); })
                .catch((error) => setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
        }, children: [_jsx("div", { className: "label", style: { marginBottom: "0.6rem" }, children: "Someone who can sign in" }), _jsx("label", { htmlFor: "p-name", children: "Name" }), _jsx("input", { id: "p-name", required: true, value: name, onChange: (e) => setName(e.target.value) }), _jsx("label", { htmlFor: "p-email", children: "Address" }), _jsx("input", { id: "p-email", type: "email", required: true, value: email, onChange: (e) => setEmail(e.target.value) }), _jsx("label", { htmlFor: "p-secret", children: "Secret" }), _jsx("input", { id: "p-secret", type: "password", required: true, minLength: 16, value: secret, onChange: (e) => setSecret(e.target.value) }), _jsx("p", { style: { fontSize: "0.8rem", color: "var(--muted)", marginTop: "-0.6rem" }, children: "Chosen here and shown to nobody afterwards, so give it to them by another route." }), said && _jsx("p", { className: "refused", style: { marginBottom: "0.8rem" }, children: said }), _jsx("button", { type: "submit", children: "Add" }), " ", _jsx("button", { type: "button", className: "quiet", onClick: () => setOpen(false), children: "Cancel" })] }));
}
function NewInstitution({ onDone }) {
    const [open, setOpen] = useState(false);
    const [slug, setSlug] = useState("");
    const [name, setName] = useState("");
    const [said, setSaid] = useState(null);
    if (!open) {
        return (_jsx("p", { style: { marginTop: "-0.6rem", marginBottom: "1.4rem" }, children: _jsx("button", { className: "quiet", onClick: () => setOpen(true), children: "Found an institution" }) }));
    }
    return (_jsxs("form", { className: "card", style: { maxWidth: "30rem", marginBottom: "1.4rem" }, onSubmit: (event) => {
            event.preventDefault();
            setSaid(null);
            api.createOrganisation(slug, name)
                .then(() => { setOpen(false); setSlug(""); setName(""); onDone(); })
                .catch((error) => setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
        }, children: [_jsx("div", { className: "label", style: { marginBottom: "0.6rem" }, children: "An institution" }), _jsx("label", { htmlFor: "o-slug", children: "Handle" }), _jsx("input", { id: "o-slug", required: true, pattern: "[a-z0-9][a-z0-9-]*[a-z0-9]", value: slug, onChange: (e) => setSlug(e.target.value) }), _jsx("label", { htmlFor: "o-name", children: "Name" }), _jsx("input", { id: "o-name", required: true, value: name, onChange: (e) => setName(e.target.value) }), said && _jsx("p", { className: "refused", style: { marginBottom: "0.8rem" }, children: said }), _jsx("button", { type: "submit", children: "Found" }), " ", _jsx("button", { type: "button", className: "quiet", onClick: () => setOpen(false), children: "Cancel" })] }));
}
/**
 * Grant and withdraw access to one place, vehicle or queue.
 *
 * Shown beside whatever it governs rather than on a screen of its own, because
 * "who may use this" is a question about the thing, not a separate subject.
 */
export function Grants({ assetId, grants, grant, revoke, noun, }) {
    const [version, setVersion] = useState(0);
    const again = () => setVersion((n) => n + 1);
    const held = useAsked(grants, [assetId, version]);
    const organisations = useAsked(() => api.organisations(), [version]);
    const people = useAsked(() => api.people(), [version]);
    const [subject, setSubject] = useState("");
    const [role, setRole] = useState("viewer");
    const [said, setSaid] = useState(null);
    const subjects = [
        ...(organisations.state === "answered"
            ? organisations.value.organisations.map((org) => ({ id: org.id, label: `${org.name} (institution)`, kind: "org" }))
            : []),
        ...(people.state === "answered"
            ? people.value.people.filter((person) => !person.disabled).map((person) => ({ id: person.id, label: `${person.displayName} (person)`, kind: "principal" }))
            : []),
    ];
    return (_jsxs(_Fragment, { children: [_jsxs("h3", { children: ["Who may use this ", noun] }), _jsx(Answered, { asked: held, empty: {
                    of: (value) => value.grants.length === 0,
                    say: `Nobody holds a grant on this ${noun}, so only those with authority at the platform can see or use it.`,
                }, children: (value) => (_jsx("div", { className: "scroll", style: { marginBottom: "0.9rem" }, children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Subject" }), _jsx("th", { children: "Kind" }), _jsx("th", { children: "Role" }), _jsx("th", { children: "Granted" }), _jsx("th", {})] }) }), _jsx("tbody", { children: value.grants.map((binding) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: nameOf(binding.subjectId, subjects) }), _jsx("td", { children: binding.subjectKind }), _jsx("td", { children: _jsx(Tag, { kind: "accent", children: binding.role }) }), _jsx("td", { children: _jsx(When, { value: binding.createdAt }) }), _jsx("td", { style: { textAlign: "right" }, children: _jsx("button", { className: "quiet", onClick: () => {
                                                    setSaid(null);
                                                    revoke(binding.id).then(again).catch((error) => setSaid(error instanceof Refused ? error.message : "Could not withdraw it."));
                                                }, children: "Withdraw" }) })] }, binding.id))) })] }) })) }), _jsxs("form", { style: { display: "flex", gap: "0.5rem", alignItems: "flex-end", flexWrap: "wrap" }, onSubmit: (event) => {
                    event.preventDefault();
                    const chosen = subjects.find((entry) => entry.id === subject);
                    if (!chosen)
                        return;
                    setSaid(null);
                    grant(chosen.kind, chosen.id, role)
                        .then(() => { setSubject(""); again(); })
                        .catch((error) => setSaid(error instanceof Refused ? error.message : "The platform could not be reached."));
                }, children: [_jsxs("span", { children: [_jsx("label", { htmlFor: `subject-${assetId}`, children: "Grant to" }), _jsxs("select", { id: `subject-${assetId}`, required: true, value: subject, onChange: (event) => setSubject(event.target.value), style: { padding: "0.42rem", font: "inherit", minWidth: "16rem" }, children: [_jsx("option", { value: "", children: "choose\u2026" }), subjects.map((entry) => (_jsx("option", { value: entry.id, children: entry.label }, entry.id)))] })] }), _jsxs("span", { children: [_jsx("label", { htmlFor: `role-${assetId}`, children: "As" }), _jsxs("select", { id: `role-${assetId}`, value: role, onChange: (event) => setRole(event.target.value), style: { padding: "0.42rem", font: "inherit" }, children: [_jsx("option", { value: "viewer", children: "viewer" }), _jsx("option", { value: "contributor", children: "contributor" }), _jsx("option", { value: "steward", children: "steward" }), _jsx("option", { value: "admin", children: "admin" })] })] }), _jsx("button", { type: "submit", disabled: subject === "", children: "Grant" })] }), said && _jsx("p", { className: "refused", style: { marginTop: "0.8rem" }, children: said })] }));
}
function nameOf(id, subjects) {
    return subjects.find((entry) => entry.id === id)?.label ?? id;
}
