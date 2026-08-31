import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCallback, useEffect, useState } from "react";
import { api, Refused } from "./api/client.js";
import { Places } from "./screens/Places.js";
import { Vehicles } from "./screens/Vehicles.js";
import { Queues } from "./screens/Queues.js";
import { Dives } from "./screens/Dives.js";
import { Refusals } from "./screens/Refusals.js";
import { Overview } from "./screens/Overview.js";
import { Access } from "./screens/Access.js";
const screens = [
    { id: "overview", label: "Overview" },
    { id: "places", label: "Places" },
    { id: "vehicles", label: "Vehicles" },
    { id: "queues", label: "Queues" },
    { id: "dives", label: "Dives" },
    { id: "access", label: "People and access" },
    { id: "refusals", label: "Refusals" },
];
function screenFromPath() {
    const first = window.location.pathname.split("/").filter(Boolean)[0];
    const known = screens.find((screen) => screen.id === first);
    return known?.id ?? "overview";
}
export function App() {
    const [signedIn, setSignedIn] = useState(undefined);
    const [screen, setScreen] = useState(screenFromPath);
    const refresh = useCallback(() => {
        api.me()
            .then(setSignedIn)
            .catch((error) => {
            // 401 is not a failure here; it is the platform saying nobody is signed
            // in, which is exactly what the sign-in screen exists for.
            if (error instanceof Refused && error.status === 401)
                setSignedIn(null);
            else
                setSignedIn(null);
        });
    }, []);
    useEffect(refresh, [refresh]);
    useEffect(() => {
        const onPop = () => setScreen(screenFromPath());
        window.addEventListener("popstate", onPop);
        return () => window.removeEventListener("popstate", onPop);
    }, []);
    const go = (next) => {
        window.history.pushState(null, "", `/${next}`);
        setScreen(next);
    };
    if (signedIn === undefined) {
        return _jsx("div", { className: "signin", children: _jsx("p", { className: "loading", children: "Asking the platform who you are\u2026" }) });
    }
    if (signedIn === null)
        return _jsx(SignIn, { onSignedIn: refresh });
    return (_jsxs("div", { className: "shell", children: [_jsxs("aside", { className: "rail", children: [_jsxs("div", { className: "mark", children: [_jsx("h1", { children: "Coral City" }), _jsx("p", { children: "control plane" })] }), _jsx("nav", { children: screens.map((entry) => (_jsx("a", { href: `/${entry.id}`, "aria-current": screen === entry.id ? "page" : undefined, onClick: (event) => { event.preventDefault(); go(entry.id); }, children: entry.label }, entry.id))) }), _jsxs("div", { className: "whoami", children: [_jsx("strong", { children: signedIn.principal.displayName }), _jsx("span", { children: signedIn.organisations.map((org) => org.name).join(", ") || "no institution" }), _jsx("p", { style: { margin: "0.6rem 0 0" }, children: _jsx("button", { className: "quiet", onClick: () => { void api.signOut().finally(() => setSignedIn(null)); }, children: "Sign out" }) })] })] }), _jsxs("main", { children: [screen === "overview" && _jsx(Overview, { organisations: signedIn.organisations }), screen === "places" && _jsx(Places, {}), screen === "vehicles" && _jsx(Vehicles, {}), screen === "queues" && _jsx(Queues, {}), screen === "dives" && _jsx(Dives, { organisations: signedIn.organisations }), screen === "access" && _jsx(Access, {}), screen === "refusals" && _jsx(Refusals, {})] })] }));
}
function SignIn({ onSignedIn }) {
    const [email, setEmail] = useState("");
    const [secret, setSecret] = useState("");
    const [refusal, setRefusal] = useState(null);
    const [busy, setBusy] = useState(false);
    const submit = (event) => {
        event.preventDefault();
        setBusy(true);
        setRefusal(null);
        api.signIn(email, secret)
            .then(onSignedIn)
            .catch((error) => {
            // The platform refuses a wrong secret and an unknown address the same
            // way, and so does this: saying which was wrong would tell somebody
            // whether an address is registered here.
            setRefusal(error instanceof Refused && error.status === 401
                ? "That address and secret were not accepted."
                : "The platform could not be reached.");
        })
            .finally(() => setBusy(false));
    };
    return (_jsx("div", { className: "signin", children: _jsxs("form", { onSubmit: submit, children: [_jsx("h1", { children: "Coral City" }), _jsx("p", { className: "lede", children: "The control plane. Resources and governance." }), _jsx("label", { htmlFor: "email", children: "Address" }), _jsx("input", { id: "email", type: "email", autoComplete: "username", required: true, value: email, onChange: (event) => setEmail(event.target.value) }), _jsx("label", { htmlFor: "secret", children: "Secret" }), _jsx("input", { id: "secret", type: "password", autoComplete: "current-password", required: true, value: secret, onChange: (event) => setSecret(event.target.value) }), refusal && _jsx("p", { className: "refused", style: { marginBottom: "1rem" }, children: refusal }), _jsx("button", { type: "submit", disabled: busy, children: busy ? "Signing in…" : "Sign in" })] }) }));
}
