"""`coral-city`: check, try, fly, deploy, dive."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import __version__, vehicles
from .loading import controller_from


def bytes_of(said: str) -> int:
    """'8G', '512M', '1.5T' or a plain number of bytes."""
    said = said.strip().upper().rstrip("B").rstrip("I")
    scale = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}
    if said and said[-1] in scale:
        return int(float(said[:-1]) * scale[said[-1]])
    return int(float(said))


def cmd_vehicles(args) -> int:
    for v in vehicles.all():
        print(f"{v.slug:16s} {v.name}: {len(v.thrusters)} thrusters, takes {', '.join(v.accepts) or 'nothing'}; "
              f"carries {', '.join(v.carries)}")
    return 0


def cmd_check(args) -> int:
    cls = controller_from(args.controller)
    controller = cls()
    vehicle = controller.described
    problems = vehicle.check(cls)
    print(f"{cls.__name__} — {cls.name!r}, for the {vehicle.name}, commanding by {cls.commands}")
    for p in controller.parameters.values():
        print(f"  tunable {p.name} = {p.value} [{p.low}, {p.high}] {p.unit}  {p.says}")
    if problems:
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("  ✓ can fly this vehicle")
    return 0


def cmd_tank(args) -> int:
    from .tank import Tank
    from .tasks import TASKS

    cls = controller_from(args.controller)
    controller = cls()
    task = None
    if args.task:
        if args.task not in TASKS:
            raise SystemExit(f"no task '{args.task}'; there are {', '.join(TASKS)}")
        task = TASKS[args.task]()
    tank = Tank(cls.vehicle, start=tuple(args.start), seconds=args.seconds, task=task, sensed=not args.truth)
    report = tank.run(controller)
    print(report)
    if args.trace:
        every = max(1, len(report.trace) // 20)
        for row in report.trace[::every]:
            print(f"  t={row['t']:6.1f}  depth {row['depthM']:6.3f}  heading {row['headingDeg']:7.1f}  "
                  f"x {row['x']:7.2f}  y {row['y']:7.2f}  reward {row['reward']:+.2f}")
    if args.json:
        print(json.dumps({"score": report.score, "final": report.final, "task": report.task}))
    return 0


def cmd_fly(args) -> int:
    from .ros import fly

    fly(controller_from(args.controller)(), rate_hz=args.rate)
    return 0


def cmd_sign_in(args) -> int:
    from .platform import Platform

    platform = Platform(args.api)
    email = args.email or input("email: ")
    secret = getpass.getpass("secret: ")
    platform.sign_in(email, secret)
    platform.keep()
    me = platform.me()
    print(f"signed in as {me['principal']['displayName']} at {args.api}; "
          f"member of {', '.join(o['slug'] for o in me['organisations'])}")
    return 0


def cmd_deploy(args) -> int:
    from .deploy import deploy

    needs = {}
    if args.gpu_memory:
        needs["gpuMemoryBytes"] = bytes_of(args.gpu_memory)
    if args.cpus:
        needs["cpu"] = args.cpus
    if args.memory:
        needs["memoryBytes"] = bytes_of(args.memory)
    stack = deploy(args.controller, args.slug, args.name or args.slug, args.push_to, args.pulled_from,
                   args.org, rate_hz=args.rate, platform_arch=args.arch, wants_gpu=args.gpu, label=args.label,
                   needs=needs)
    print(json.dumps({"id": stack["id"], "slug": stack["slug"], "imageDigest": stack["imageDigest"]}))
    return 0


def cmd_dive(args) -> int:
    from .platform import Platform

    platform = Platform.from_session()
    institution = platform.organisation(args.org)
    stack = platform.stack(institution["id"], args.stack) if args.stack else None
    place = platform.city(args.place)
    vehicle = platform.vehicle(args.vehicle)
    city_version = platform.published(platform.city_versions(place["id"]))
    vehicle_version = platform.published(platform.vehicle_versions(vehicle["id"]))
    conditions = platform.conditions(institution["id"])
    queues = platform.queues()
    if not queues:
        raise SystemExit("no queue you may run on")
    queue = next((q for q in queues if args.queue in (q["slug"], q["id"])), queues[0]) if args.queue else queues[0]

    name = args.name or f"{stack['name'] if stack else 'Nobody'} flies the {vehicle.get('name', args.vehicle)} in {place.get('name', args.place)}"
    objective = None
    if args.task:
        from .tasks import TASKS
        if args.task not in TASKS:
            raise SystemExit(f"no task '{args.task}'; there are {', '.join(TASKS)}")
        objective = TASKS[args.task]()
    dive = platform.define_dive(institution["id"], name, city_version["id"], vehicle_version["id"],
                                conditions["id"], stack["id"] if stack else None, objective=objective)
    run = platform.run(dive["id"], queue["id"], mode="interactive" if args.interactive else "batch")
    print(f"dive {dive['id']}  run {run['id']}  ({run['state']}, {run['mode']})")
    if args.no_wait:
        return 0

    def tell(event):
        detail = event.get("detail") or {}
        short = {k: v for k, v in detail.items() if k in (
            "depthM", "speedMs", "commanded", "commandsReceived", "host", "signalPort", "why", "t", "task", "kind", "score")}
        print(f"  {event.get('kind'):22s} {json.dumps(short) if short else ''}")

    if args.interactive:
        print("interactive: the run stays up until you cancel it or leave the console")
        run = platform.wait(dive["id"], run["id"], timeout=args.timeout, tell=tell,
                            until_state=("running", "succeeded", "failed", "expired", "cancelled"))
        print(json.dumps({"state": run["state"], "diveId": dive["id"], "runId": run["id"]}))
        return 0
    run = platform.wait(dive["id"], run["id"], timeout=args.timeout, tell=tell)
    print(json.dumps({"state": run["state"], "outcome": run.get("outcome", {})}))
    return 0 if run["state"] == "succeeded" else 1


def cmd_fetch(args) -> int:
    from .platform import Platform

    platform = Platform.from_session()
    count = platform.fetch(args.dive, args.run, args.into,
                           tell=lambda path, size: print(f"  {path}  {size / 1024:.1f} KB"))
    print(f"{count} files into {args.into}")
    return 0 if count else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="coral-city", description="Write a controller, try it, deploy it, fly it.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("vehicles", help="the vehicles the catalogue describes").set_defaults(go=cmd_vehicles)

    p = sub.add_parser("check", help="whether a controller can fly its vehicle")
    p.add_argument("controller", help="path/to/file.py[:Class] or module[:Class]")
    p.set_defaults(go=cmd_check)

    p = sub.add_parser("tank", help="run a controller headless in the runtime's physics")
    p.add_argument("controller")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--start", type=float, nargs=3, default=[0.0, 0.0, -7.0], metavar=("X", "Y", "Z"))
    p.add_argument("--task", help="hold | waypoints | transect | survey | return")
    p.add_argument("--truth", action="store_true", help="hand the controller the true state, not what its sensors would say")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(go=cmd_tank)

    p = sub.add_parser("fly", help="run a controller live over ROS 2")
    p.add_argument("controller")
    p.add_argument("--rate", type=float, default=20.0)
    p.set_defaults(go=cmd_fly)

    p = sub.add_parser("sign-in", help="keep a session with a platform")
    p.add_argument("--api", default="http://localhost:18080")
    p.add_argument("--email")
    p.set_defaults(go=cmd_sign_in)

    p = sub.add_parser("deploy", help="package a controller as an image and register it as autonomy")
    p.add_argument("controller")
    p.add_argument("--slug", required=True)
    p.add_argument("--name")
    p.add_argument("--push-to", default="localhost:18081", help="registry to push to, as seen from here")
    p.add_argument("--pulled-from", help="the same registry as the platform's hosts see it (default: as pushed)")
    p.add_argument("--org")
    p.add_argument("--rate", type=float, default=20.0)
    p.add_argument("--arch", default="linux/amd64")
    p.add_argument("--gpu", action="store_true", help="the controller needs a GPU for inference")
    p.add_argument("--gpu-memory", help="how much of a card it needs, e.g. 8G; implies --gpu")
    p.add_argument("--cpus", type=float, help="processors it needs (default 2)")
    p.add_argument("--memory", help="host memory it needs, e.g. 4G (default 4G)")
    p.add_argument("--label")
    p.set_defaults(go=cmd_deploy)

    p = sub.add_parser("dive", help="define a dive with a stack and run it")
    p.add_argument("--stack", help="autonomy slug or id; none means the dive is held by the runtime")
    p.add_argument("--task", help="what the dive is for: hold | waypoints | transect | survey | return")
    p.add_argument("--place", required=True)
    p.add_argument("--vehicle", required=True)
    p.add_argument("--org")
    p.add_argument("--queue")
    p.add_argument("--name")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--timeout", type=float, default=900.0)
    p.set_defaults(go=cmd_dive)

    p = sub.add_parser("fetch", help="download what a run left behind: its recording")
    p.add_argument("dive")
    p.add_argument("run")
    p.add_argument("--into", default="recording")
    p.set_defaults(go=cmd_fetch)

    args = parser.parse_args(argv)
    return args.go(args)


if __name__ == "__main__":
    sys.exit(main())
