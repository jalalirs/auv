import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";
/**
 * What the platform has refused you, and why.
 *
 * A refusal is recorded rather than merely returned, so that somebody who
 * cannot do a thing can find out what authority it would have needed instead of
 * guessing.
 */
export function Refusals() {
    const denials = useAsked(() => api.denials(), []);
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Refusals" }), _jsx("p", { className: "lede", children: "Every refusal you have received. A visible refusal says the thing exists and access may be requested; a hidden one says only that nothing is there, because saying more would itself disclose something." }), _jsx(Answered, { asked: denials, empty: {
                    of: (value) => value.denials.length === 0,
                    say: "The platform has refused you nothing.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Action" }), _jsx("th", { children: "On" }), _jsx("th", { children: "Effect" }), _jsx("th", { children: "Reason" }), _jsx("th", { children: "When" })] }) }), _jsx("tbody", { children: value.denials.map((denial) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: denial.action }), _jsx("td", { className: "mono", children: denial.resourceKind }), _jsx("td", { children: denial.effect === "visible"
                                                ? _jsx(Tag, { kind: "warn", children: "may be requested" })
                                                : _jsx(Tag, { kind: "idle", children: "reported absent" }) }), _jsx("td", { children: denial.reason }), _jsx("td", { children: _jsx(When, { value: denial.occurredAt }) })] }, denial.id))) })] }) })) })] }));
}
