// What a vehicle's parameters mean.
//
// The same arithmetic the runner integrates, done once here so a page can say
// what the numbers imply — how the vehicle sits in the water, how fast it can
// go before drag matches thrust, which way each thruster pushes — and so that
// changing a number on the page shows its consequence before anybody publishes
// a version. Nothing here is a simulation; these are the closed-form
// quantities that follow from the parameters.
//
// Conventions match the runner and the catalogue: body frame x forward, y to
// starboard, z up; the six axes are surge, sway, heave, roll, pitch, yaw.

import type { VehicleDynamics } from "@coral-city/api";

export const AXES = ["surge", "sway", "heave", "roll", "pitch", "yaw"] as const;
export type Axis = (typeof AXES)[number];

const G = 9.81;
const SEAWATER_KG_M3 = 1025;

export interface Thruster {
  name: string;
  position: [number, number, number];
  direction: [number, number, number];
}

/** The thruster block of the dynamics, with the shape the catalogue writes. */
export interface Thrusters {
  model?: string;
  maxForwardN: number;
  maxReverseN: number;
  timeConstantS?: number;
  units: Thruster[];
}

export function thrustersOf(dynamics: VehicleDynamics): Thrusters {
  const t = dynamics.thrusters as unknown as Partial<Thrusters>;
  return {
    model: t.model,
    maxForwardN: t.maxForwardN ?? 0,
    maxReverseN: t.maxReverseN ?? 0,
    timeConstantS: t.timeConstantS,
    units: (t.units ?? []).map((u) => ({
      name: u.name, position: u.position, direction: u.direction,
    })),
  };
}

function diagonal(block: unknown): number[] {
  const d = (block as { diagonal?: number[] } | undefined)?.diagonal;
  return Array.isArray(d) ? d.map(Number) : [0, 0, 0, 0, 0, 0];
}

export interface Buoyancy {
  weightN: number;
  buoyancyN: number;
  netN: number;
  /** Positive floats, negative sinks. */
  netKg: number;
  /** Metres the centre of buoyancy sits above the centre of gravity: the righting arm. */
  rightingArmM: number;
  sits: "floats" | "sinks" | "neutral";
}

export function buoyancyOf(d: VehicleDynamics): Buoyancy {
  const weightN = d.massKg * G;
  const buoyancyN = d.displacedVolumeM3 * SEAWATER_KG_M3 * G;
  const netN = buoyancyN - weightN;
  const arm = (d.centreOfBuoyancyM[2] ?? 0) - (d.centreOfGravityM[2] ?? 0);
  return {
    weightN, buoyancyN, netN, netKg: netN / G, rightingArmM: arm,
    sits: Math.abs(netN) < 0.05 * weightN * 0.02 ? "neutral" : netN > 0 ? "floats" : "sinks",
  };
}

/**
 * Each thruster's contribution to the six axes: a column of the allocation
 * matrix. Force along its direction, moment from its position crossed with it.
 */
export function wrenchOf(unit: Thruster): number[] {
  const [px, py, pz] = unit.position;
  const [dx, dy, dz] = unit.direction;
  const length = Math.hypot(dx, dy, dz) || 1;
  const fx = dx / length, fy = dy / length, fz = dz / length;
  return [fx, fy, fz, py * fz - pz * fy, pz * fx - px * fz, px * fy - py * fx];
}

export interface AxisAuthority {
  axis: Axis;
  /** The most force (N) or moment (N·m) the thrusters can put on this axis together, in each sense. */
  positive: number;
  negative: number;
  /** The units that contribute at all. */
  contributors: number;
}

/** What the thrusters can muster on each axis, all of them pushing the same way. */
export function authorityOf(t: Thrusters): AxisAuthority[] {
  return AXES.map((axis, k) => {
    let positive = 0, negative = 0, contributors = 0;
    for (const unit of t.units) {
      const w = wrenchOf(unit)[k]!;
      if (Math.abs(w) < 1e-6) continue;
      contributors += 1;
      // Pushing forward on a unit gives w * maxForward; reversing gives -w * maxReverse.
      positive += Math.max(w * t.maxForwardN, -w * t.maxReverseN);
      negative += Math.max(-w * t.maxForwardN, w * t.maxReverseN);
    }
    return { axis, positive, negative, contributors };
  });
}

export interface AxisSpeed {
  axis: Axis;
  /** The steady speed (m/s or rad/s) at which drag equals the available force, each way. */
  positive: number;
  negative: number;
  /** Effective mass on this axis: the vehicle's plus the water it drags along. */
  effectiveMass: number;
  linear: number;
  quadratic: number;
}

/**
 * Terminal speed per axis: solve  Xu·v + Xuu·v|v| + F = 0  for v, with the
 * damping coefficients negative by the catalogue's convention.
 */
export function speedsOf(d: VehicleDynamics, authority: AxisAuthority[]): AxisSpeed[] {
  const added = diagonal(d.addedMass);
  const lin = diagonal(d.linearDamping);
  const quad = diagonal(d.quadraticDamping);
  const inertia = d.inertiaTensor as number[];
  return AXES.map((axis, k) => {
    const a = Math.abs(quad[k] ?? 0), b = Math.abs(lin[k] ?? 0);
    const terminal = (force: number): number => {
      if (force <= 0) return 0;
      if (a < 1e-9) return b < 1e-9 ? Infinity : force / b;
      // a v² + b v − F = 0
      return (-b + Math.sqrt(b * b + 4 * a * force)) / (2 * a);
    };
    const own = k < 3 ? d.massKg : (inertia[k < 3 ? 0 : (k - 3) * 4] ?? 0);
    return {
      axis,
      positive: terminal(authority[k]!.positive),
      negative: terminal(authority[k]!.negative),
      effectiveMass: own + Math.abs(added[k] ?? 0),
      linear: lin[k] ?? 0, quadratic: quad[k] ?? 0,
    };
  });
}

/** Everything a page shows about a vehicle, derived in one go. */
export interface Derived {
  buoyancy: Buoyancy;
  thrusters: Thrusters;
  authority: AxisAuthority[];
  speeds: AxisSpeed[];
  /** Metres the vehicle spans in x, y, z, from where its thrusters are. */
  reachM: [number, number, number];
}

export function derive(d: VehicleDynamics): Derived {
  const thrusters = thrustersOf(d);
  const authority = authorityOf(thrusters);
  const reach: [number, number, number] = [0, 0, 0];
  for (const unit of thrusters.units) {
    for (let k = 0; k < 3; k++) reach[k] = Math.max(reach[k]!, 2 * Math.abs(unit.position[k]!));
  }
  return { buoyancy: buoyancyOf(d), thrusters, authority, speeds: speedsOf(d, authority), reachM: reach };
}

/** A copy with one top-level number changed, for the what-if fields on the page. */
export function withNumber(d: VehicleDynamics, key: "massKg" | "displacedVolumeM3", value: number): VehicleDynamics {
  return { ...d, [key]: value };
}

export function withThrust(d: VehicleDynamics, maxForwardN: number, maxReverseN: number): VehicleDynamics {
  const thrusters = { ...(d.thrusters as unknown as object), maxForwardN, maxReverseN };
  return { ...d, thrusters: thrusters as unknown as VehicleDynamics["thrusters"] };
}
