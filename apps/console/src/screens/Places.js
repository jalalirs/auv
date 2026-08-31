import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Digest, Tag, When } from "./parts.js";
import { Grants } from "./Access.js";
/** The places a dive can happen in, and who may enter them. */
export function Places() {
    const [opened, setOpened] = useState(null);
    const cities = useAsked(() => api.cities(), []);
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Places" }), _jsx("p", { className: "lede", children: "A place exists at the platform and outlives the institutions granted access to it. One that is neither discoverable nor granted to you is not listed here, and is indistinguishable from one that does not exist." }), _jsx(Answered, { asked: cities, empty: {
                    of: (value) => value.cities.length === 0,
                    say: "No place is visible to you. Places you have not been granted are not listed, and undiscoverable places are not listed at all.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Handle" }), _jsx("th", { children: "Name" }), _jsx("th", { children: "Vertical datum" }), _jsx("th", { children: "Listing" }), _jsx("th", { children: "Founded" })] }) }), _jsx("tbody", { children: value.cities.map((city) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: _jsx("a", { href: "#", onClick: (event) => {
                                                    event.preventDefault();
                                                    setOpened(opened === city.id ? null : city.id);
                                                }, children: city.slug }) }), _jsx("td", { children: city.name }), _jsx("td", { children: city.verticalDatum }), _jsx("td", { children: city.discoverable
                                                ? _jsx(Tag, { kind: "idle", children: "discoverable" })
                                                : _jsx(Tag, { kind: "accent", children: "granted only" }) }), _jsx("td", { children: _jsx(When, { value: city.createdAt }) })] }, city.id))) })] }) })) }), opened && _jsx(AssetDetail, { id: opened, noun: "place", versions: () => api.cityVersions(opened), grants: () => api.cityGrants(opened), grantTo: (kind, subject, role) => api.grantCity(opened, kind, subject, role), revokeFrom: (bindingId) => api.revokeCityGrant(opened, bindingId) }, opened)] }));
}
/** A place's or a vehicle's packages, and who holds a grant on it. */
export function AssetDetail({ id, noun, versions, grants, grantTo, revokeFrom, }) {
    const packaged = useAsked(versions, [id]);
    return (_jsxs(_Fragment, { children: [_jsx("h3", { children: "Packages" }), _jsx(Answered, { asked: packaged, empty: {
                    of: (value) => value.versions.length === 0,
                    say: "Nothing has been packaged for this yet. A dive names a published package, so until there is one, nothing can be flown here.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "#" }), _jsx("th", { children: "Label" }), _jsx("th", { children: "Digest" }), _jsx("th", { children: "Size" }), _jsx("th", { children: "State" }), _jsx("th", { children: "Recorded" })] }) }), _jsx("tbody", { children: value.versions.map((version) => (_jsxs("tr", { children: [_jsx("td", { className: "num", children: version.ordinal }), _jsx("td", { children: version.label || _jsx("span", { style: { color: "var(--muted)" }, children: "unlabelled" }) }), _jsx("td", { children: _jsx(Digest, { value: version.digest }) }), _jsxs("td", { className: "num", children: [(version.totalBytes / 1024).toFixed(1), " KiB"] }), _jsx("td", { children: version.publishedAt
                                                ? _jsx(Tag, { kind: "good", children: "published" })
                                                : _jsx(Tag, { kind: "warn", children: "draft" }) }), _jsx("td", { children: _jsx(When, { value: version.createdAt }) })] }, version.id))) })] }) })) }), _jsx(Grants, { assetId: id, noun: noun, grants: grants, grant: (kind, subject, role) => grantTo(kind, subject, role), revoke: revokeFrom })] }));
}
