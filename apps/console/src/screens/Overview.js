import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered } from "./parts.js";
/**
 * What the platform holds, at a glance.
 *
 * Every number here is one the platform said. Where a count would need a
 * question this caller may not ask, it is absent rather than guessed.
 */
export function Overview({ organisations }) {
    const build = useAsked(() => api.platform(), []);
    const cities = useAsked(() => api.cities(), []);
    const vehicles = useAsked(() => api.vehicles(), []);
    const queues = useAsked(() => api.queues(), []);
    const free = queues.state === "answered"
        ? queues.value.queues.reduce((sum, queue) => sum + queue.free, 0) : undefined;
    const devices = queues.state === "answered"
        ? queues.value.queues.reduce((sum, queue) => sum + queue.devices, 0) : undefined;
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Overview" }), _jsx("p", { className: "lede", children: "What this installation holds, and what of it you may see. A place or a vehicle nobody has granted you does not appear here and is not counted." }), _jsxs("div", { className: "cards", children: [_jsxs("div", { className: "card", children: [_jsx("div", { className: "label", children: "Places" }), _jsx("div", { className: "value", children: cities.state === "answered" ? cities.value.cities.length : "—" }), _jsx("div", { className: "note", children: "visible to you" })] }), _jsxs("div", { className: "card", children: [_jsx("div", { className: "label", children: "Vehicles" }), _jsx("div", { className: "value", children: vehicles.state === "answered" ? vehicles.value.vehicles.length : "—" }), _jsx("div", { className: "note", children: "visible to you" })] }), _jsxs("div", { className: "card", children: [_jsx("div", { className: "label", children: "Hardware" }), _jsxs("div", { className: "value", children: [free ?? "—", _jsxs("span", { style: { fontSize: "1rem", color: "var(--muted)" }, children: [" / ", devices ?? "—"] })] }), _jsx("div", { className: "note", children: "devices free" })] }), _jsxs("div", { className: "card", children: [_jsx("div", { className: "label", children: "Institutions" }), _jsx("div", { className: "value", children: organisations.length }), _jsx("div", { className: "note", children: "you belong to" })] })] }), _jsx("h3", { children: "This installation" }), _jsx(Answered, { asked: build, children: (info) => (_jsx("div", { className: "scroll", children: _jsx("table", { children: _jsxs("tbody", { children: [_jsxs("tr", { children: [_jsx("th", { style: { width: "12rem" }, children: "Service" }), _jsx("td", { children: info.name })] }), _jsxs("tr", { children: [_jsx("th", { children: "Version" }), _jsx("td", { className: "mono", children: info.version })] }), _jsxs("tr", { children: [_jsx("th", { children: "Commit" }), _jsx("td", { className: "mono", children: info.commit })] }), _jsxs("tr", { children: [_jsx("th", { children: "Built" }), _jsx("td", { className: "mono", children: info.builtAt })] })] }) }) })) })] }));
}
