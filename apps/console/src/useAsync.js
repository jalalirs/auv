import { useEffect, useState } from "react";
import { Refused } from "./api/client.js";
/**
 * Ask the platform for something, and keep the refusal if it refuses.
 *
 * A refusal is not an error: it is the platform saying something true about
 * what the caller may know, and screens show it as such rather than as a
 * failure of theirs.
 */
export function useAsked(ask, deps) {
    const [asked, setAsked] = useState({ state: "asking" });
    useEffect(() => {
        let current = true;
        setAsked({ state: "asking" });
        ask()
            .then((value) => { if (current)
            setAsked({ state: "answered", value }); })
            .catch((error) => {
            if (!current)
                return;
            if (error instanceof Refused)
                setAsked({ state: "refused", refusal: error });
            else
                setAsked({ state: "broken", error: error });
        });
        return () => { current = false; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
    return asked;
}
