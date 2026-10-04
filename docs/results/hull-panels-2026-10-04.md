# Hull drag panel by panel: checked against the BlueROV2, 4 October 2026

`hardware/hull_panels.py <hull.usd> --into <package>` · `hardware/hull_panels.py --check`

r6 item 14's next round. The coefficient model gives each axis its own drag as the square of its speed, and a rotation's drag could not be taken from a hull: estimated from a silhouette it came out five to twenty times under what was measured (docs/results/hull-coefficients-2026-10-03.md). The panel model takes the drag from the hull's panels instead. Each panel meets the water at its own velocity — the vehicle's, plus its turn times its arm — and pushes back:

- a face meeting the water: 0.8 of the stagnation pressure, inward;
- a face leaving it, where it opens on the wake: 0.37 of it as suction.

Together those are a flat plate's 1.17 (Hoerner). Each panel's exposure, from each of 26 directions, is worked out once from the mesh by casting a ray towards the oncoming water. A panel behind another part meets slowed water (the wake share). A panel the water reaches from none of the ways it faces is inside the hull and is dropped. The runtime (`services/sim-runtime/coral/panels.py`) sums force and moment over the panels every step. Translation, rotation and the two together come from the same sum.

## The check

The BlueROV2 Heavy's mesh (1,556 panels) against Li et al. (2020), the standard BlueROV2 held on load cells in a current. One number is fitted: the wake share, to their measured surge of about 45 N at 1 m/s (read off their figure; they give no table). It comes out at 0.97: water passes the parts behind in an open frame nearly undiminished.

| | panels | Li et al. |
|---|---|---|
| surge, 1.0 m/s | 45.0 N (fitted) | ≈ 45 N measured; 39.5 N their fit |
| sway, 0.6 m/s | **28.2 N** | **≈ 30 N measured**; 52.2 N their fit (CFD) |
| heave, 0.6 m/s | 28.2 N | 88.8 N their fit (CFD only) |
| yaw, quadratic | 0.49 N·m/(rad/s)² | 4.86 (CFD); Wu 2018: 1.5 |

Sway, not fitted, is within 6 % of what was measured. Heave sits well under their CFD, as it did with the silhouette, and nothing measured was there to check it against. Yaw is twice the silhouette's 0.24 and still a third of Wu's identification. So where a package's own rotational damping is larger, the runtime adds the difference: the ducts and interference no panel sees.

## Where it is used

**The BlueROV2 Heavy only** (`catalog/vehicles/bluerov2-heavy/panels.json`). That is the open frame it was checked on.

Mini-hoot and Boxfish Luna stay on their hull coefficients. With the one wake share fitted on an open frame, mini-hoot's closed moulded hull comes out at about twice its silhouette's drag (26 against 12 N in surge at 1 m/s). A closed body's wake is not an open frame's. For a closed hull, though, the silhouette estimate is the measured one: its drag coefficients are Hoerner's tow-tank and wind-tunnel measurements of closed bluff bodies, by length over width. So each kind of hull is flown on the model checked against its own kind: open frames on panels (Li et al.), closed hulls on Hoerner's silhouettes. A tow test of mini-hoot itself would still beat both. The standard BlueROV2 has no mesh.

## Tried and not taken: a wake from measured tandem bodies

Fitting the wake share once was meant to be replaced by measurement. Tandem circular cylinders (Alam et al. 2003, Re 6.5×10⁴) keep no drag closer than about 3.5 diameters behind another, 0.23 at 4.5 and 0.30 at 9. Each shielded panel was given that, by how far it sits behind the part shielding it, over that part's width. Nothing was fitted.

On the Heavy this gives 23.7 N of surge at 1 m/s and 17.2 N of sway at 0.6 m/s, against Li et al.'s measured 45 and 30: about half. A long two-dimensional cylinder's wake recovers far more slowly than the wake of a short member in an open frame, which water reaches from every side. So the cylinder data does not carry over, and the fitted share, which does reproduce the measurement, stays. No measured drag for a small closed-hull hovering vehicle could be found either (searched 4 October: SUR-II, WIEVLE and ODIN-III report only CFD), which leaves Hoerner's closed bodies as the reference for closed hulls.

## Sources

- Li, Q., Cao, Y., Li, B., Ingram, D. M., Kiprakis, A. (2020). Numerical modelling and experimental testing of the hydrodynamic characteristics for an open-frame remotely operated vehicle. *J. Mar. Sci. Eng.* 8, 688.
- Wu, C.-J. (2018). *6-DoF Modelling and Control of a Remotely Operated Vehicle*. Flinders University.
- Hoerner, S. F. (1965). *Fluid-Dynamic Drag*.
- Alam, M. M., Moriya, M., Takai, K., Sakamoto, H. (2003). Fluctuating fluid forces acting on two circular cylinders in a tandem arrangement at a subcritical Reynolds number. *J. Wind Eng. Ind. Aerodyn.* 91, 139–154.
