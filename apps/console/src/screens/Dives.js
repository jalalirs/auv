import { jsx as _jsx, Fragment as _Fragment, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Digest, Tag, When } from "./parts.js";
function stateTag(state) {
    switch (state) {
        case "succeeded": return _jsx(Tag, { kind: "good", children: "succeeded" });
        case "running": return _jsx(Tag, { kind: "good", children: "running" });
        case "preparing": return _jsx(Tag, { kind: "warn", children: "preparing" });
        case "queued": return _jsx(Tag, { kind: "idle", children: "queued" });
        case "failed": return _jsx(Tag, { kind: "bad", children: "failed" });
        case "cancelled": return _jsx(Tag, { kind: "idle", children: "cancelled" });
        case "expired": return _jsx(Tag, { kind: "bad", children: "expired" });
        default: return _jsx(Tag, { kind: "idle", children: state });
    }
}
/** What an institution has composed, and what its runs did. */
export function Dives({ organisations }) {
    const [orgId, setOrgId] = useState(organisations[0]?.id ?? "");
    const [opened, setOpened] = useState(null);
    const dives = useAsked(() => api.dives(orgId), [orgId]);
    const autonomy = useAsked(() => api.autonomy(orgId), [orgId]);
    if (organisations.length === 0) {
        return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Dives" }), _jsx("div", { className: "empty", children: "You do not belong to an institution, and a dive belongs to one." })] }));
    }
    return (_jsxs(_Fragment, { children: [_jsx("h2", { children: "Dives" }), _jsx("p", { className: "lede", children: "A dive is a vehicle in a place, under conditions, flown by autonomy. It names package versions rather than assets, so publishing a newer vehicle does not silently turn an experiment into a different one." }), organisations.length > 1 && (_jsxs("p", { style: { marginBottom: "1.2rem" }, children: [_jsx("label", { htmlFor: "org", children: "Institution" }), _jsx("select", { id: "org", value: orgId, onChange: (event) => setOrgId(event.target.value), style: { padding: "0.4rem", font: "inherit" }, children: organisations.map((org) => _jsx("option", { value: org.id, children: org.name }, org.id)) })] })), _jsx(Answered, { asked: dives, empty: {
                    of: (value) => value.dives.length === 0,
                    say: "This institution has composed no dives. A dive needs a published place, a published vehicle, and conditions before it can be defined.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Name" }), _jsx("th", { children: "Place" }), _jsx("th", { children: "Vehicle" }), _jsx("th", { children: "Autonomy" }), _jsx("th", { children: "Defined" })] }) }), _jsx("tbody", { children: value.dives.map((plan) => (_jsxs("tr", { children: [_jsx("td", { children: _jsx("a", { href: "#", onClick: (event) => {
                                                    event.preventDefault();
                                                    setOpened(opened === plan.id ? null : plan.id);
                                                }, children: plan.name }) }), _jsxs("td", { className: "mono", children: [plan.cityVersionId.slice(0, 12), "\u2026"] }), _jsxs("td", { className: "mono", children: [plan.vehicleVersionId.slice(0, 12), "\u2026"] }), _jsx("td", { children: plan.autonomyStackId
                                                ? _jsx(Tag, { kind: "accent", children: "brought" })
                                                : _jsx("span", { style: { color: "var(--muted)" }, children: "none" }) }), _jsx("td", { children: _jsx(When, { value: plan.createdAt }) })] }, plan.id))) })] }) })) }), opened && _jsx(RunsOf, { diveId: opened }, opened), _jsx("h3", { children: "Autonomy this institution has registered" }), _jsx(Answered, { asked: autonomy, empty: {
                    of: (value) => value.autonomy.length === 0,
                    say: "No autonomy has been registered. A stack is a container image pinned by digest, never by tag, so that re-running a dive re-runs the same program.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Handle" }), _jsx("th", { children: "Name" }), _jsx("th", { children: "Image" }), _jsx("th", { children: "Digest" }), _jsx("th", { children: "GPU" })] }) }), _jsx("tbody", { children: value.autonomy.map((stack) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: stack.slug }), _jsx("td", { children: stack.name }), _jsx("td", { className: "mono", children: stack.imageRepository }), _jsx("td", { children: _jsx(Digest, { value: stack.imageDigest.replace("sha256:", "") }) }), _jsx("td", { children: stack.wantsGpu ? _jsx(Tag, { kind: "warn", children: "shares one" }) : _jsx(Tag, { kind: "idle", children: "none" }) })] }, stack.id))) })] }) })) })] }));
}
/** The states a run can still be stopped from. Everything else is history. */
const LIVE = new Set(["queued", "preparing", "running"]);
function RunsOf({ diveId }) {
    // Counted rather than a refetch on the hook, because asking again is asking
    // again: the same question, with something about the world now different.
    const [since, askAgain] = useState(0);
    const runs = useAsked(() => api.runs(diveId), [diveId, since]);
    const [ending, setEnding] = useState();
    const [refusal, setRefusal] = useState("");
    async function end(runId) {
        setEnding(runId);
        setRefusal("");
        try {
            await api.cancelRun(diveId, runId);
            // Asked for again rather than edited in place: what a run's state is now
            // is the platform's answer, and a screen that decided for itself would
            // show "cancelled" for something the agent had not let go of yet.
            askAgain((n) => n + 1);
        }
        catch (problem) {
            setRefusal(problem instanceof Error ? problem.message : "that did not work");
        }
        finally {
            setEnding(undefined);
        }
    }
    return (_jsxs(_Fragment, { children: [_jsx("h3", { children: "Runs" }), refusal === "" ? null : _jsx("p", { className: "refusal", children: refusal }), _jsx("p", { className: "lede", style: { marginBottom: "0.8rem" }, children: "A run copies every determinant when it is admitted \u2014 the digests, the seed, the runtime \u2014 so that editing the dive afterwards cannot change what a recorded result means. The same seed and the same digests is the same run." }), _jsx(Answered, { asked: runs, empty: {
                    of: (value) => value.runs.length === 0,
                    say: "This dive has never been run.",
                }, children: (value) => (_jsx("div", { className: "scroll", children: _jsxs("table", { children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "State" }), _jsx("th", { children: "Mode" }), _jsx("th", { children: "Seed" }), _jsx("th", { children: "Runtime" }), _jsx("th", { children: "Place" }), _jsx("th", { children: "Vehicle" }), _jsx("th", { children: "Requested" }), _jsx("th", {})] }) }), _jsx("tbody", { children: value.runs.map((run) => (_jsxs("tr", { children: [_jsx("td", { children: stateTag(run.state) }), _jsx("td", { children: run.mode === "interactive" ? _jsx(Tag, { kind: "accent", children: "interactive" }) : _jsx(Tag, { kind: "idle", children: "batch" }) }), _jsx("td", { className: "mono num", children: run.seed }), _jsx("td", { className: "mono", children: run.runtimeVersion }), _jsx("td", { children: _jsx(Digest, { value: run.cityDigest }) }), _jsx("td", { children: _jsx(Digest, { value: run.vehicleDigest }) }), _jsx("td", { children: _jsx(When, { value: run.requestedAt }) }), _jsx("td", { children: LIVE.has(run.state) && (_jsx("button", { className: "quiet small", disabled: ending === run.id, onClick: () => void end(run.id), children: ending === run.id ? "ending…" : "End" })) })] }, run.id))) })] }) })) })] }));
}
