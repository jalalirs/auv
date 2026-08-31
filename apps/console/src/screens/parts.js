import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * What a screen shows while it is asking, when it was refused, and when there
 * is nothing to show.
 *
 * A refusal is kept rather than flattened into an error, because it is often
 * the most informative answer a screen can give: a hidden refusal reports
 * absence, and a visible one says the thing exists and may be asked for.
 */
export function Answered({ asked, empty, children, }) {
    if (asked.state === "asking")
        return _jsx("p", { className: "loading", children: "Asking the platform\u2026" });
    if (asked.state === "refused") {
        return (_jsxs("div", { className: "refused", children: [_jsx("strong", { children: asked.refusal.problem?.message ?? "The platform refused this." }), asked.refusal.mayBeRequested
                    ? "This exists and access to it may be requested."
                    : "Either it does not exist, or it is not yours to know about. The platform does not distinguish the two."] }));
    }
    if (asked.state === "broken") {
        return _jsxs("div", { className: "refused", children: [_jsx("strong", { children: "The platform could not be reached." }), asked.error.message] });
    }
    if (empty && empty.of(asked.value))
        return _jsx("div", { className: "empty", children: empty.say });
    return _jsx(_Fragment, { children: children(asked.value) });
}
export function Tag({ kind, children }) {
    return _jsx("span", { className: `tag tag-${kind}`, children: children });
}
/** A digest is long and only its first characters are ever compared by eye. */
export function Digest({ value }) {
    if (!value)
        return _jsx("span", { style: { color: "var(--muted)" }, children: "\u2014" });
    return _jsxs("code", { title: value, children: [value.slice(0, 12), "\u2026"] });
}
export function When({ value }) {
    if (!value)
        return _jsx("span", { style: { color: "var(--muted)" }, children: "\u2014" });
    const at = new Date(value);
    return _jsx("span", { title: at.toISOString(), children: at.toLocaleString() });
}
