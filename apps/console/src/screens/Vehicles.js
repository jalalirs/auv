import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";
import { AssetDetail } from "./Places.js";
/** The vehicles the platform publishes, and who may fly them. */
export function Vehicles() {
    const [opened, setOpened] = useState(null);
    const vehicles = useAsked(() => api.vehicles(), []);
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Vehicles" }), _jsx("p", { className: "lede", children: "Vehicles are the platform's to publish and to grant. What a person brings is autonomy, not a hull. A vehicle version must state how it moves before it can be published, so that nothing is ever flown by a model that does not exist." }), _jsx(Answered, { asked: vehicles, empty: {
                    of: (value) => value.vehicles.length === 0,
                    say: "No vehicle is visible to you. Vehicles you have not been granted are not listed, and undiscoverable ones are not listed at all.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Handle" }), _jsx("th", { children: "Name" }), _jsx("th", { children: "Maker" }), _jsx("th", { children: "Listing" }), _jsx("th", { children: "Published" })] }) }), _jsx("tbody", { children: value.vehicles.map((vehicle) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: _jsx("a", { href: "#", onClick: (event) => {
                                                    event.preventDefault();
                                                    setOpened(opened === vehicle.id ? null : vehicle.id);
                                                }, children: vehicle.slug }) }), _jsx("td", { children: vehicle.name }), _jsx("td", { children: vehicle.manufacturer || _jsx("span", { style: { color: "var(--muted)" }, children: "\u2014" }) }), _jsx("td", { children: vehicle.discoverable
                                                ? _jsx(Tag, { kind: "idle", children: "discoverable" })
                                                : _jsx(Tag, { kind: "accent", children: "granted only" }) }), _jsx("td", { children: _jsx(When, { value: vehicle.createdAt }) })] }, vehicle.id))) })] }) })) }), opened && _jsx(AssetDetail, { id: opened, noun: "vehicle", versions: () => api.vehicleVersions(opened), grants: () => api.vehicleGrants(opened), grantTo: (kind, subject, role) => api.grantVehicle(opened, kind, subject, role), revokeFrom: (bindingId) => api.revokeVehicleGrant(opened, bindingId) }, opened)] }));
}
