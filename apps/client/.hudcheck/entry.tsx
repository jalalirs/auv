import { createRoot } from "react-dom/client";
import { Hud } from "/Users/jalalirs/code/auv/apps/client/src/renderer/parts/Hud.js";

declare const TOLD: any;
const root = createRoot(document.getElementById("hud")!);
root.render(<Hud {...TOLD} />);
