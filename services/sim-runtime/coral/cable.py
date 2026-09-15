"""The shape a cable takes in moving water.

Lifted out of `tether.py` because a mooring line is the same problem: a limp
thing between two points, pushed by the water and pulled down by its own
weight, and the answer is where it ends up. The tether has one end on a vehicle
that moves and a limit on how far that vehicle can get; a mooring line has both
ends fixed. Everything between those two statements is this file.

Quasi-static: a light line settles far faster than anything manoeuvres near it,
so the shape is relaxed to equilibrium rather than integrated. Drag is on the
component of the water's motion *across* the line — the cross-flow principle
that cable people use — which is what makes a line lean downstream rather than
balloon.

The displacement is the point. A hundred-metre mooring line with ten per cent
of slack hangs fourteen metres below the straight line between its ends in
still water; put half a knot across it and it goes somewhere else again. A
vehicle flying the chart's line meets neither.
"""

from __future__ import annotations

import numpy as np

# Seawater. The difference over any working range is under half a per cent and
# a line's drag coefficient is not known to better than ten.
DENSITY = 1025.0

# A cylinder across the flow, at the Reynolds numbers a cable sees.
DRAG_NORMAL = 1.2


def lay_out(a, b, length: float, nodes: int, current=None) -> np.ndarray:
    """A first shape between two points, with the slack already in it.

    Not a straight line. A straight line is the one shape a slack cable cannot
    be — every segment is in compression, which a cable cannot carry — and a
    relaxation started there has nothing to tell it which way to bulge. It gets
    there eventually from rounding, and eventually is hundreds of passes.

    So the slack goes in at the start, as the parabola a span of this much line
    makes, leaning the way the water is going: a near-neutral line is pushed
    far harder than it is pulled down.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    walk = np.linspace(0.0, 1.0, nodes)[:, None]
    shape = a[None, :] * (1 - walk) + b[None, :] * walk

    span = float(np.linalg.norm(b - a))
    if span < 1e-6 or length <= span:
        return shape
    # A parabola of span d and sag s is about d(1 + 8s²/3d²) long.
    sag = span * float(np.sqrt(3.0 * (length / span - 1.0) / 8.0))
    way = np.array([0.0, 0.0, -1.0])
    if current is not None:
        flow = np.asarray(current, dtype=float)
        speed = float(np.linalg.norm(flow))
        if speed > 1e-3:
            way = flow / speed
    shape[1:-1] += ((4.0 * walk * (1.0 - walk)) * sag * way[None, :])[1:-1]
    return shape


def load_on(shape: np.ndarray, current, segment: float,
            diameter: float, weight_n_per_m: float,
            drag_normal: float = DRAG_NORMAL) -> np.ndarray:
    """The force on each node: its weight in water, and its drag.

    Only the component of the water's motion across the line. A cable edge-on
    to the flow is not being pushed, and it is this that makes a line lean
    downstream rather than balloon.
    """
    current = np.asarray(current, dtype=float)
    along = np.zeros_like(shape)
    along[1:-1] = shape[2:] - shape[:-2]
    along[0] = shape[1] - shape[0]
    along[-1] = shape[-1] - shape[-2]
    length = np.linalg.norm(along, axis=1, keepdims=True)
    along = np.divide(along, np.where(length < 1e-9, 1.0, length))

    flow = np.tile(current, (len(shape), 1))
    across = flow - along * np.sum(flow * along, axis=1, keepdims=True)
    speed = np.linalg.norm(across, axis=1, keepdims=True)
    drag = 0.5 * DENSITY * drag_normal * (diameter * segment) * speed * across

    weight = np.zeros_like(shape)
    weight[:, 2] = -weight_n_per_m * segment
    return drag + weight


def relax(shape: np.ndarray, segment: float, ends: tuple[bool, bool] = (True, True),
          sweeps: int | None = None) -> None:
    """Pull the nodes back to a segment apart, with the pinned ends held.

    Position-based rather than elastic: a working cable stretches under a per
    cent at the loads it sees, and a stiff spring at two hundred hertz is a
    spring that explodes. What this cannot model is a shock load, which is the
    taut case and is handled as a limit instead.

    Swept as many times as the chain is long, because a correction made at one
    end takes one sweep to travel one node. Two sweeps is plenty for twenty
    nodes and nowhere near enough for a hundred: a hundred-node mooring line
    relaxed twice a pass stretched to seventy-six metres of lateral excursion
    on a span that had nineteen metres of slack in it — the constraint could
    not propagate as fast as the drag pushed.
    """
    last = len(shape) - 1
    if sweeps is None:
        sweeps = max(2, last // 4)
    for _ in range(sweeps):
        for i in range(last):
            first = 0.0 if (i == 0 and ends[0]) else 0.5
            second = 0.0 if (i + 1 == last and ends[1]) else 0.5
            share = first + second
            if share <= 0.0:
                continue
            a, b = shape[i], shape[i + 1]
            apart = b - a
            length = float(np.linalg.norm(apart))
            if length < 1e-9:
                continue
            correct = (length - segment) / length * apart
            shape[i] = a + correct * (first / share)
            shape[i + 1] = b - correct * (second / share)


def settle(shape: np.ndarray, a, b, length: float, current,
           diameter: float, weight_n_per_m: float, passes: int,
           drag_normal: float = DRAG_NORMAL, sweeps: int | None = None) -> np.ndarray:
    """Put the line where the water leaves it, with both ends pinned.

    `sweeps` is how rigid the length constraint is: a correction made at one
    end travels one node a sweep, so a chain is only truly inextensible when it
    is swept as many times as it is long. That is what a cold solve wants and
    what a correction to an already-settled shape does not, so a solve from
    nothing says so and the per-step correction takes the cheap default.
    """
    shape[0] = np.asarray(a, dtype=float)
    shape[-1] = np.asarray(b, dtype=float)
    segment = length / (len(shape) - 1)
    for _ in range(passes):
        load = load_on(shape, current, segment, diameter, weight_n_per_m, drag_normal)
        # A displacement rather than an acceleration: this is a relaxation
        # towards equilibrium and not an integration through time, and giving a
        # cable inertia it does not need is how a quasi-static solver rings.
        #
        # Clamped to a fraction of a segment, because the size of the step must
        # not depend on the size of the force. It did, and a line in half a
        # knot was pushed further each pass than the length constraint could
        # pull back: a hundred-metre span with ten metres of slack in it
        # settled at a hundred and thirty-five metres of arc, which is not a
        # cable, it is a cable being stretched by its own solver.
        step = load * (segment * 0.02)
        far = np.linalg.norm(step, axis=1, keepdims=True)
        step = np.divide(step, np.where(far > segment * 0.05, far / (segment * 0.05), 1.0))
        shape[1:-1] += step[1:-1]
        relax(shape, segment, sweeps=sweeps)
    shape[0] = np.asarray(a, dtype=float)
    shape[-1] = np.asarray(b, dtype=float)
    return shape


def tension_along(shape: np.ndarray, load: np.ndarray):
    """The tension in every segment, from the balance at every node.

    At equilibrium each node balances the pull of the segment above it, the
    pull of the segment below it, and what the water and its own weight do:

        T_i·û_i − T_{i−1}·û_{i−1} + f_i = 0

    Three equations a node in however many segments there are — heavily
    overdetermined, solved as a least squares.

    The obvious cheaper thing is the whole cable's equilibrium instead: two end
    tensions, three equations, done. That is *ill-posed exactly where it
    matters*. A cable that streams out and comes back has both ends pulling
    along nearly the same line, the two unknowns stop being independent, and
    the split swings on rounding — the same cable answered 6 N, then 10, then
    13 as the shape was relaxed further, while the shape itself had stopped
    moving.

    Answers the tensions and the unit vector of each segment, or nothing when
    the shape has collapsed.
    """
    segments = shape[1:] - shape[:-1]
    length = np.linalg.norm(segments, axis=1, keepdims=True)
    if float(length.min()) < 1e-9:
        return None, None
    along = segments / length
    nodes = len(shape) - 2
    rows = np.zeros((nodes * 3, len(along)))
    answer = np.zeros(nodes * 3)
    for i in range(nodes):
        node = i + 1
        for axis in range(3):
            rows[i * 3 + axis, node] = along[node][axis]
            rows[i * 3 + axis, node - 1] = -along[node - 1][axis]
            answer[i * 3 + axis] = -load[node][axis]
    tensions, *_ = np.linalg.lstsq(rows, answer, rcond=None)
    return tensions, along
