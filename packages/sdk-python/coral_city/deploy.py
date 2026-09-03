"""One command from a controller file to autonomy the platform will fly.

Packages the controller as an image on the ROS 2 distribution with this SDK
inside it, pushes it to a registry the platform's hosts can pull from, and
registers it — by digest, never by tag — as an autonomy stack of your
institution, with the topics it will use taken from the vehicle it was written
for. Registering it under the institution is what grants it: every member can
then define a dive with it.

The image links against nothing of the platform's. It is the same container
that would run beside a real vehicle.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

from .loading import controller_from
from .platform import Platform

DOCKERFILE = """\
# Built by `coral-city deploy`. The controller and the SDK ride on the ROS 2
# distribution; nothing of the platform's is inside.
FROM ros:jazzy-ros-core

RUN apt-get update \\
 && apt-get install -y --no-install-recommends python3-numpy \\
 && rm -rf /var/lib/apt/lists/*

COPY sdk/coral_city /opt/coral_city_sdk/coral_city
COPY controller.py /opt/controller/controller.py
ENV PYTHONPATH=/opt/coral_city_sdk:/opt/controller
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/bin/bash", "-lc", "source /opt/ros/jazzy/setup.bash && exec python3 -m coral_city.ros controller:{cls} --rate {rate}"]
"""


def build_context(controller_path: pathlib.Path, class_name: str, rate_hz: float, out: pathlib.Path) -> None:
    sdk = pathlib.Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(controller_path, out / "controller.py")
    shutil.copytree(sdk, out / "sdk" / "coral_city", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (out / "Dockerfile").write_text(DOCKERFILE.format(cls=class_name, rate=rate_hz))


def run(command: list[str], quiet: bool = False) -> str:
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"{' '.join(command[:2])} failed:\n{done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.strip()


def digest_of(reference: str) -> str:
    said = run(["docker", "inspect", "--format", "{{json .RepoDigests}}", reference])
    for entry in json.loads(said):
        if "@" in entry:
            return entry.split("@", 1)[1]
    raise SystemExit(f"{reference} has no digest; was it pushed?")


def deploy(controller_spec: str, slug: str, name: str, push_to: str, pulled_from: str | None,
           org: str | None, platform: Platform | None = None, rate_hz: float = 20.0,
           platform_arch: str = "linux/amd64", wants_gpu: bool = False, label: str | None = None,
           needs: dict | None = None, tell=print) -> dict:
    cls = controller_from(controller_spec)
    controller = cls()
    vehicle = controller.described
    problems = vehicle.check(cls)
    if problems:
        raise SystemExit(f"{cls.__name__} cannot fly the {vehicle.name}: " + "; ".join(problems))

    path = pathlib.Path(controller_spec.split(":")[0]).resolve()
    reference = f"{push_to.rstrip('/')}/{slug}:{label or 'latest'}"
    with tempfile.TemporaryDirectory() as folder:
        context = pathlib.Path(folder)
        build_context(path, cls.__name__, rate_hz, context)
        tell(f"building {reference} for {platform_arch}…")
        run(["docker", "build", "--quiet", "--platform", platform_arch, "-t", reference, str(context)])
    tell("pushing…")
    run(["docker", "push", "--quiet", reference])
    digest = digest_of(reference)
    repository = f"{(pulled_from or push_to).rstrip('/')}/{slug}"
    tell(f"pushed as {repository}@{digest[:19]}…")

    # What it will use, from the vehicle it was written for: every sensor the
    # node subscribes to, and the one command topic it publishes.
    subscribes = ["/depth", "/imu/data"] + (["/dvl/twist"] if "dvl" in vehicle.carries else [])
    publishes = ["/cmd_vel" if cls.commands == "wrench" else "/thruster_cmd"]

    platform = platform or Platform.from_session()
    institution = platform.organisation(org)
    # Each registration is a build of the controller the slug names, pinned by
    # digest; dives pin a build by id, so earlier dives keep theirs.
    stack = platform.register_autonomy(institution["id"], slug, name, repository, digest,
                                       subscribes, publishes, wants_gpu or bool(needs.get("gpu")), needs)
    tell(f"registered as {stack['id']} ({stack['slug']}) in {institution['name']}")
    return stack
