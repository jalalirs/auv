# Hull drag from the hull itself: checked against the BlueROV2, 3 October 2026

`hardware/hull_coefficients.py <hull.usd> [--dynamics dynamics.json]`

Every vehicle on the platform flies Fossen's coefficient model. Until now the coefficients were the BlueROV2's, scaled to each vehicle by its volume and frontal area, so the hull's shape did not enter. This is r6 item 14: estimate the coefficients from the hull, and check the estimate against published measurements before trusting it.

## How the estimate works

The standard engineering estimates made before a tow tank:

- **Quadratic drag, each translation.** ½ ρ C_D A. A is the hull's silhouette seen along that axis, rasterised at 2 mm; holes in an open frame are not counted as area. C_D is a bluff body's, taken from its length along the flow over its width (Hoerner, *Fluid-Dynamic Drag*, ch. 3).
- **Quadratic drag, each rotation.** The same drag on every element of the two silhouettes the rotation sweeps, each moving at ωr: ½ ρ C_D ∫ |r|³ dA.
- **Added mass.** That of the ellipsoid with the hull's extents (Lamb; Imlay 1961 for the rotations), scaled by how solid the silhouettes are.
- **Linear drag.** Not derived; it is left as each package has it.

## The check: a BlueROV2 Heavy mesh against three published sets

Units: kg; N/(m/s)²; N·m/(rad/s)².

| | this, Heavy mesh | Wu 2018, Heavy (system ID) | Wu 2018, standard (system ID) | Li et al. 2020, standard (current tank + CFD) |
|---|---|---|---|---|
| surge quadratic | **39.0** | 141 | 18.2 | 38.2 (measured ≈ 45 N at 1 m/s) |
| sway quadratic | 46.2 | 217 | 21.7 | 129.7 (CFD; measured ≈ 30 N at 0.6 m/s) |
| heave quadratic | 117.6 | 190 | 37.0 | 243.3 (CFD) |
| roll quadratic | 0.56 | 1.19 | 1.55 | — |
| pitch quadratic | 0.29 | 0.47 | 1.55 | — |
| yaw quadratic | 0.24 | 1.5 | 1.55 | 4.86 (CFD) |
| surge added mass | 12.5 | 6.36 | 5.5 | — |
| sway added mass | 8.7 | 7.12 | 12.7 | — |
| heave added mass | 37.6 | 18.68 | 14.57 | — |

The mesh is the Heavy configuration, 457 × 566 × 254 mm. Its silhouettes are 0.087 / 0.103 / 0.200 m², with C_D 0.88 / 0.87 / 1.15.

**The references disagree with each other more than with the estimate.**

- Wu's two identifications differ by about 8× in surge (18.2 against 141), for frames whose frontal areas differ by 1.7×.
- 141 N/(m/s)² means C_D·A = 0.275 m², nearly twice the Heavy's whole frontal box (0.144 m²). A bluff body's C_D does not exceed about 1.2, so that number cannot be quadratic drag alone; it must carry some thruster or identification effect.
- Li et al. measured the drag directly, holding the vehicle on load cells in a current. That is the most physical reference.

**Against Li et al.:**

- **Surge.** The estimate (39, for the somewhat larger Heavy) is within about 15 % of what they measured: ≈ 45 N at 1 m/s on the standard frame.
- **Sway and heave.** The estimate is about half their CFD. Water entering an open frame hits the parts behind the silhouette (thrusters, battery tube, frame members), and a silhouette cannot see them. For an open frame these are therefore a lower bound.
- **Rotations.** The estimate is 5 to 20 times under every reference (yaw: 0.24 against 1.5 and 4.86). The strip integral misses whatever carries the measured rotational damping: thruster ducts, interference, possibly the props.

## What the packages now take

**Translational quadratic drag only.** Surge, sway and heave are taken from the hull. Roll, pitch and yaw stay the BlueROV2's scaled (assumed), as do added mass and linear drag. Each package's note says so. `hardware/mini/package.py` and `hardware/luna/package.py` call `hull_coefficients.drag_for` on their own hull.

| vehicle | surge | sway | heave | was (scaled BlueROV2) |
|---|---|---|---|---|
| mini-hoot (moulded hull) | 12.4 | 18.8 | 31.0 | 7.1 / 8.6 / 20.5 |
| Boxfish Luna (frame and cylinder) | 54.6 | 105.6 | 123.5 | 32.3 / 47.8 / 76.0 |

Mini-hoot's hull is closed, which is where a silhouette estimate is best. Luna's is half open, so her sway and heave are lower bounds.

**Regression.** Mini-hoot's tank round trip takes 87 s, up from 76 s, and still reaches 5 of 5. Luna's Looe Key transect ends 1.08 m short, against 1.07 m before.

## Still to do

- **Better rotations and added mass.** These need either a panel method (Capytaine, for added mass) or a CFD run, and a measured rotation decay (Li et al.'s free-decay method) to check against.
- **The next round's per-panel model.** It replaces this coefficient model with forces computed on the hull's panels in the local water every step. It should be checked against Li et al.'s force-speed curves first, since they are the measured reference.

## Sources

- Wu, C.-J. (2018). *6-DoF Modelling and Control of a Remotely Operated Vehicle*. Flinders University thesis.
- Li, Q., Cao, Y., Li, B., Ingram, D. M., Kiprakis, A. (2020). Numerical modelling and experimental testing of the hydrodynamic characteristics for an open-frame remotely operated vehicle. *J. Mar. Sci. Eng.* 8, 688. doi:10.3390/jmse8090688
- Hoerner, S. F. (1965). *Fluid-Dynamic Drag*.
- Imlay, F. H. (1961). *The complete expressions for added mass of a rigid body moving in an ideal fluid*. DTMB report 1528.
