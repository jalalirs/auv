// The vehicles we know the physics of, whether or not the platform can fly them.
//
// The platform publishes vehicles as packages and grants them; that is what
// the fleet page lists first. Beside them are the vehicles from this
// repository's catalogue whose parameters have a published source but which
// have no hull package yet, or which need a capability the runner does not
// have. They are shown so that their physics can be read and compared, and
// marked, unmistakably, as not yet flyable.
//
// The dynamics are imported from the catalogue itself, so the numbers on the
// page are the numbers in the file.

import type { VehicleDynamics } from "@coral-city/api";

import bluerov2 from "../../../../../catalog/vehicles/bluerov2/dynamics.json";
import bluerov2Heavy from "../../../../../catalog/vehicles/bluerov2-heavy/dynamics.json";
import remus100 from "../../../../../catalog/vehicles/remus-100/dynamics.json";

export interface CataloguedVehicle {
  slug: string;
  name: string;
  manufacturer: string;
  summary: string;
  /** What the numbers rest on. */
  source: string;
  dynamics: VehicleDynamics;
  /** Why it cannot be flown yet, or nothing if the platform's package is what decides. */
  notYet?: string;
}

export const CATALOGUE: CataloguedVehicle[] = [
  {
    slug: "bluerov2",
    name: "BlueROV2",
    manufacturer: "Blue Robotics",
    summary: "Observation-class ROV, six vectored thrusters.",
    source: "Published values commonly cited for the vehicle; manufacturer's thruster figures at 16 V.",
    dynamics: bluerov2 as unknown as VehicleDynamics,
  },
  {
    slug: "bluerov2-heavy",
    name: "BlueROV2 Heavy",
    manufacturer: "Blue Robotics",
    summary: "The heavy configuration: eight thrusters, with roll and pitch authority the standard frame lacks.",
    source: "Wu, C.-J. (2018), 6-DoF Modelling and Control of a Remotely Operated Vehicle, Flinders University.",
    dynamics: bluerov2Heavy as unknown as VehicleDynamics,
    notYet: "no hull package yet",
  },
  {
    slug: "remus-100",
    name: "REMUS 100",
    manufacturer: "Hydroid / Kongsberg",
    summary: "Torpedo survey AUV: one propeller, four fins, the reference vehicle of the control literature.",
    source: "Prestero, T. (2001), Verification of a Six-Degree of Freedom Simulation Model for the REMUS AUV, MIT/WHOI.",
    dynamics: remus100 as unknown as VehicleDynamics,
    notYet: "steers with fins, which the allocator does not model yet",
  },
];

export function catalogued(slug: string): CataloguedVehicle | undefined {
  return CATALOGUE.find((v) => v.slug === slug);
}
