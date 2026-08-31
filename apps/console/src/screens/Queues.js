import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";
import { Grants } from "./Access.js";
/** The hardware, and who may submit to it. */
export function Queues() {
    const [opened, setOpened] = useState(null);
    const queues = useAsked(() => api.queues(), []);
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Queues" }), _jsx("p", { className: "lede", children: "The governed resource is the queue, not the device: a queue holds however many devices it holds, so adding hardware is an insert rather than a change to the platform. Hardware carries no discoverability \u2014 somebody who cannot run on a queue has no reason to learn it exists." }), _jsx(Answered, { asked: queues, empty: {
                    of: (value) => value.queues.length === 0,
                    say: "No queue is visible to you. Hardware is granted, never discovered, so a queue nobody has granted you is indistinguishable from one that does not exist.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Handle" }), _jsx("th", { children: "Name" }), _jsx("th", { children: "Free" }), _jsx("th", { children: "Lease" }), _jsx("th", { children: "State" }), _jsx("th", { children: "Opened" })] }) }), _jsx("tbody", { children: value.queues.map((queue) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: _jsx("a", { href: "#", onClick: (event) => {
                                                    event.preventDefault();
                                                    setOpened(opened === queue.id ? null : queue.id);
                                                }, children: queue.slug }) }), _jsx("td", { children: queue.name }), _jsx("td", { className: "num", children: queue.devices === 0
                                                ? _jsx("span", { style: { color: "var(--muted)" }, children: "no hardware" })
                                                : _jsxs(_Fragment, { children: [queue.free, " of ", queue.devices] }) }), _jsxs("td", { className: "num", children: [Math.round(queue.leaseSeconds / 60), " min"] }), _jsx("td", { children: queue.draining
                                                ? _jsx(Tag, { kind: "warn", children: "draining" })
                                                : queue.free > 0
                                                    ? _jsx(Tag, { kind: "good", children: "accepting" })
                                                    : _jsx(Tag, { kind: "idle", children: "full" }) }), _jsx("td", { children: _jsx(When, { value: queue.createdAt }) })] }, queue.id))) })] }) })) }), opened && _jsx(QueueDetail, { id: opened }, opened)] }));
}
function QueueDetail({ id }) {
    const devices = useAsked(() => api.devices(id), [id]);
    return (_jsxs(_Fragment, { children: [_jsx("h3", { children: "Devices" }), _jsx(Answered, { asked: devices, empty: {
                    of: (value) => value.devices.length === 0,
                    say: "This queue holds no hardware. An agent registers what it found when it starts, so an empty queue usually means no agent has reported one yet.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Index" }), _jsx("th", { children: "Model" }), _jsx("th", { children: "Memory" }), _jsx("th", { children: "UUID" }), _jsx("th", { children: "Host" }), _jsx("th", { children: "State" })] }) }), _jsx("tbody", { children: value.devices.map((device) => (_jsxs("tr", { children: [_jsx("td", { className: "num", children: device.deviceIndex }), _jsx("td", { children: device.model || _jsx("span", { style: { color: "var(--muted)" }, children: "\u2014" }) }), _jsxs("td", { className: "num", children: [(device.memoryBytes / 1024 ** 3).toFixed(0), " GiB"] }), _jsx("td", { className: "mono", children: device.uuid }), _jsx("td", { className: "mono", children: device.targetId }), _jsx("td", { children: device.enabled ? _jsx(Tag, { kind: "good", children: "enabled" }) : _jsx(Tag, { kind: "bad", children: "disabled" }) })] }, device.id))) })] }) })) }), _jsx(Grants, { assetId: id, noun: "queue", grants: () => api.queueGrants(id), grant: (kind, subject, role) => api.grantQueue(id, kind, subject, role), revoke: (bindingId) => api.revokeQueueGrant(id, bindingId) })] }));
}
