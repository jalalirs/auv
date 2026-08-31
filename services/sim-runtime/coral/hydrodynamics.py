"""Six-degree-of-freedom hydrodynamics for an underwater vehicle.

OceanSim contributes the sensors — an imaging sonar and a camera that models
absorption and backscatter — and they are the hard part of simulating
underwater perception. What it does not contribute is a vehicle: it disables
gravity and applies two damping constants, which is enough to fly a sensor rig
through a scene and not enough to test autonomy, because the thing being tested
is how a controller copes with a body that has inertia, buoyancy and drag.

This is that body. It follows Fossen's formulation, which is the standard one
for marine craft:

    (M_RB + M_A) v̇ + (C_RB(v) + C_A(v)) v + D(v) v + g(η) = τ

The terms, and where each is handled:

  M_RB    rigid-body mass and inertia          PhysX, from the vehicle package
  M_A     added mass — water accelerated       here, folded into the mass the
          along with the hull                  integrator divides by
  C       Coriolis and centripetal             neglected, deliberately (below)
  D(v)    drag, linear and quadratic           here
  g(η)    weight and buoyancy                  here, and gravity is switched ON
  τ       what the thrusters produce           here, from allocation

Two approximations are made on purpose, and both are stated where they are
made rather than buried: the added-mass matrix is treated as diagonal, and the
Coriolis and centripetal terms are dropped. Neither is right in general. Both
are defensible for a slow, nearly symmetric survey ROV and neither is
defensible for a vehicle doing several knots, which is why they are written
down where somebody changing the vehicle will read them.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field

import numpy as np

# Seawater at survey depth and temperature. Fresh water is 998, and the eight
# per cent difference is more than the uncertainty in the drag coefficients, so
# a tank test and an ocean dive are not interchangeable.
DENSITY_SEAWATER = 1025.0
DENSITY_FRESHWATER = 998.0
GRAVITY = 9.80665


@dataclass
class Thruster:
    """One thruster: where it is, which way it pushes, and how hard."""

    name: str
    position: np.ndarray
    direction: np.ndarray
    max_forward_n: float
    max_reverse_n: float

    def wrench(self, command: float) -> tuple[np.ndarray, np.ndarray]:
        """The force and moment a normalised command produces, in the body frame.

        A T200 pushes harder forwards than backwards — about 51 N against 40 —
        so a controller that assumes symmetry will trim to one side. Modelling
        the asymmetry is the difference between a vehicle that flies straight
        and one whose operator learns to fight it.
        """
        command = float(np.clip(command, -1.0, 1.0))
        magnitude = command * (self.max_forward_n if command >= 0 else self.max_reverse_n)
        force = self.direction * magnitude
        return force, np.cross(self.position, force)


@dataclass
class Hydrodynamics:
    """The parameters a vehicle package carries, ready to integrate."""

    mass_kg: float
    displaced_volume_m3: float
    centre_of_gravity: np.ndarray
    centre_of_buoyancy: np.ndarray

    added_mass: np.ndarray          # 6, diagonal of M_A
    linear_damping: np.ndarray      # 6, diagonal of D_l
    quadratic_damping: np.ndarray   # 6, diagonal of D_q

    thrusters: list[Thruster] = field(default_factory=list)
    density: float = DENSITY_SEAWATER

    @classmethod
    def from_package(cls, path: str | pathlib.Path, density: float = DENSITY_SEAWATER
                     ) -> "Hydrodynamics":
        """Read what the platform published for this vehicle.

        The parameters come from the package rather than this file so that
        changing how a vehicle behaves means publishing a new version of it,
        which a run then pins — and two runs that disagree can be told apart.
        """
        document = json.loads(pathlib.Path(path).read_text())
        units = document.get("thrusters", {})
        return cls(
            mass_kg=float(document["massKg"]),
            displaced_volume_m3=float(document["displacedVolumeM3"]),
            centre_of_gravity=np.array(document["centreOfGravityM"], dtype=float),
            centre_of_buoyancy=np.array(document["centreOfBuoyancyM"], dtype=float),
            added_mass=np.abs(np.array(document["addedMass"]["diagonal"], dtype=float)),
            linear_damping=np.abs(np.array(document["linearDamping"]["diagonal"], dtype=float)),
            quadratic_damping=np.abs(
                np.array(document["quadraticDamping"]["diagonal"], dtype=float)),
            thrusters=[
                Thruster(
                    name=unit["name"],
                    position=np.array(unit["position"], dtype=float),
                    direction=np.array(unit["direction"], dtype=float),
                    max_forward_n=float(units.get("maxForwardN", 50.0)),
                    max_reverse_n=float(units.get("maxReverseN", 40.0)),
                )
                for unit in units.get("units", [])
            ],
            density=density,
        )

    def __post_init__(self) -> None:
        if np.allclose(self.centre_of_gravity, self.centre_of_buoyancy):
            raise ValueError(
                "the centres of gravity and buoyancy coincide, which leaves the "
                "vehicle no restoring moment: it would hold any attitude it was "
                "pushed into, and do so silently")
        # Signs are a convention that differs between sources, and a sign error
        # here reads as a vehicle that accelerates for ever rather than as a
        # crash. Magnitudes are taken and the sign applied where the term is
        # used, so the convention cannot be got wrong twice.
        for name, value in (("added mass", self.added_mass),
                            ("linear damping", self.linear_damping),
                            ("quadratic damping", self.quadratic_damping)):
            if value.shape != (6,):
                raise ValueError(f"{name} has {value.shape} terms; six are needed")

    @property
    def weight_n(self) -> float:
        """What the vehicle weighs in air."""
        return self.mass_kg * GRAVITY

    @property
    def buoyancy_n(self) -> float:
        """What the water pushes back with when fully submerged."""
        return self.density * GRAVITY * self.displaced_volume_m3

    @property
    def net_buoyancy_n(self) -> float:
        """Positive means it floats. A survey ROV is trimmed slightly positive so
        that a power failure ends with it on the surface rather than on the
        bottom, and that choice belongs to whoever ballasted the vehicle rather
        than to this model."""
        return self.buoyancy_n - self.weight_n


class Body:
    """A vehicle being integrated, holding what must persist between steps."""

    def __init__(self, model: Hydrodynamics) -> None:
        self.model = model

    def restoring(self, rotation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Weight and buoyancy, in the body frame.

        Both act along the world vertical whatever the vehicle's attitude, which
        is why they are rotated into the body frame rather than treated as
        constants: it is exactly this that rights the vehicle when it rolls.

        `rotation` is the body-to-world rotation matrix.
        """
        up_in_body = rotation.T @ np.array([0.0, 0.0, 1.0])

        weight = -self.model.weight_n * up_in_body
        buoyancy = self.model.buoyancy_n * up_in_body

        moment = (np.cross(self.model.centre_of_gravity, weight)
                  + np.cross(self.model.centre_of_buoyancy, buoyancy))
        return weight + buoyancy, moment

    def damping(self, velocity: np.ndarray) -> np.ndarray:
        """Drag, as a wrench in the body frame.

        Linear drag dominates at the speeds a survey ROV works at; quadratic
        drag dominates once it is moving. Heave has by far the largest
        coefficient because the frame presents its widest face to vertical
        motion, and a controller that does not know that will overshoot every
        depth change.
        """
        linear = self.model.linear_damping * velocity
        quadratic = self.model.quadratic_damping * np.abs(velocity) * velocity
        return -(linear + quadratic)

    def effective_mass(self) -> np.ndarray:
        """Mass and inertia including the water that moves with the hull.

        Added mass is not a force. It is a statement that accelerating this
        body means accelerating some water too, and for a neutrally buoyant
        vehicle it is comparable to the hull itself — the BlueROV2's heave
        added mass is 14.6 kg against 11.5 kg of vehicle. The honest way to
        express that is to make the body heavier to accelerate, which is what
        this returns and what the integrator divides by.

        Applying it as a force instead is possible and wrong: the force depends
        on acceleration, acceleration depends on the force, and estimating one
        from differenced velocity makes a loop that diverges whenever the added
        mass exceeds the hull mass. It does exceed it here, on the axis that
        matters most for a vehicle holding depth.

        The diagonal treatment is still an approximation — the real added-mass
        matrix has off-diagonal terms coupling sway with yaw and heave with
        pitch — but it is a stable one, and the coupling is small for a hull
        this close to symmetric.
        """
        return np.concatenate([
            np.full(3, self.model.mass_kg) + self.model.added_mass[:3],
            self.model.added_mass[3:],
        ])

    def thrust(self, commands: np.ndarray) -> np.ndarray:
        """What the thrusters produce, as a wrench in the body frame."""
        force = np.zeros(3)
        moment = np.zeros(3)
        for thruster, command in zip(self.model.thrusters, commands):
            unit_force, unit_moment = thruster.wrench(command)
            force += unit_force
            moment += unit_moment
        return np.concatenate([force, moment])

    def step(self, rotation: np.ndarray, velocity: np.ndarray,
             commands: np.ndarray, dt: float) -> np.ndarray:
        """Everything the water and the thrusters do this step, as one wrench.

        `velocity` is the body-frame twist: linear then angular.

        Added mass is deliberately not in here. It belongs in the mass the
        integrator divides by — see effective_mass — because it is a change to
        what the body's inertia is rather than a force acting on it.

        Coriolis and centripetal terms are not here. They scale with the square
        of velocity and matter for a vehicle turning hard at speed; a survey ROV
        at a quarter of a metre per second is not that vehicle, and including
        them badly would be worse than leaving them out honestly. A vehicle that
        does several knots needs them, and needs this function changed.
        """
        del dt  # kept in the signature: a Coriolis term would need it.

        force, moment = self.restoring(rotation)
        wrench = np.concatenate([force, moment])
        wrench = wrench + self.damping(velocity)
        if len(self.model.thrusters) > 0:
            wrench = wrench + self.thrust(commands)
        return wrench


class Allocator:
    """Turns a wanted wrench into per-thruster commands.

    A controller would rather say "go forward and yaw left" than name six
    thruster values, and the mapping between the two is a property of where the
    thrusters are — so it belongs to the vehicle rather than to whoever is
    flying it.

    The pseudo-inverse gives the least-effort set of commands that produces the
    wanted wrench, or the closest achievable one when the wrench is not
    achievable at all. Saturating afterwards is the crude part: it changes the
    direction of the resulting wrench, so a saturated command does not merely
    produce less of what was asked for but something slightly different. A
    controller that saturates often is asking for more than the vehicle has.
    """

    def __init__(self, model: Hydrodynamics) -> None:
        if not model.thrusters:
            raise ValueError("a vehicle with no thrusters cannot be flown")
        self.model = model

        # Column per thruster: the wrench it produces at full forward thrust.
        columns = []
        for thruster in model.thrusters:
            force, moment = thruster.wrench(1.0)
            columns.append(np.concatenate([force, moment]))
        self.matrix = np.column_stack(columns)
        self.inverse = np.linalg.pinv(self.matrix)

    def capability(self) -> np.ndarray:
        """The most this vehicle can produce on each axis, on its own.

        Found by asking for one unit on an axis, seeing what commands that
        needs, and scaling until the largest of them is at the stop. It is a
        property of where the thrusters are, so it is answered here.

        Needed because a person at the controls asks for a fraction — half
        ahead, full rise — and a fraction is not a wrench. Handing 0.55 to an
        allocator that reads newtons asks a hundred-newton vehicle for half a
        newton, which is what it did: the keys reached the thrusters, the
        display said somebody was flying, and the vehicle sat still.
        """
        most = np.zeros(6)
        for axis in range(6):
            want = np.zeros(6)
            want[axis] = 1.0
            commands = self.inverse @ want
            largest = float(np.max(np.abs(commands)))
            # An axis nothing can move stays at zero rather than at infinity.
            most[axis] = 0.0 if largest < 1e-9 else 1.0 / largest
        return most

    def allocate(self, wrench: np.ndarray) -> np.ndarray:
        """Commands in [-1, 1], one per thruster."""
        return np.clip(self.inverse @ wrench, -1.0, 1.0)

    def achievable(self, wrench: np.ndarray, tolerance: float = 1e-3) -> bool:
        """Whether the vehicle can actually produce this, within tolerance.

        Useful to a controller that would rather know it is asking for the
        impossible than watch the vehicle drift.
        """
        produced = self.matrix @ self.allocate(wrench)
        scale = max(float(np.linalg.norm(wrench)), 1.0)
        return bool(np.linalg.norm(produced - wrench) / scale < tolerance)


def terminal_velocity(model: Hydrodynamics, axis: int = 2) -> float:
    """The speed at which drag balances net buoyancy on one axis.

    A vehicle released with the thrusters off rises or sinks until drag matches
    the imbalance, and the answer is a number somebody can check against a real
    vehicle without instrumenting anything: drop it, time it, compare. Solving
    D_l v + D_q v |v| = F.
    """
    force = abs(model.net_buoyancy_n)
    if force == 0.0:
        return 0.0
    linear = model.linear_damping[axis]
    quadratic = model.quadratic_damping[axis]
    if quadratic == 0.0:
        return force / linear if linear else math.inf
    # Positive root of q v² + l v − F = 0.
    return (-linear + math.sqrt(linear * linear + 4.0 * quadratic * force)) / (2.0 * quadratic)
