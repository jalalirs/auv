"""What leaves the dive: the ROS 2 bridge, and the record.

Neither changes anything in the world. Both run at the end of the tick, on the
state it produced, and both read the dive through what it says about itself —
the bridge through `publish`, the record through the dive's own reporting —
because what goes out has to agree with what the console shows, and both are
written once, there.

    bridge    Reads the sonar's ping, the clock.   Writes bridge (the port).
              The sonar's fan when it pinged, and the vehicle's state ten
              times a second: a real DVL reports at tens of hertz, not two
              hundred, and a stack tuned against a sensor that never lies
              about its rate will be surprised by one that does.
    record    Reads everything the tick wrote.     Writes record.
              The recording (recording.py) and, every five seconds of
              simulated time, the dive's state on its log — simulated, not
              wall-clock, so two runs of the same seed keep the same record.
"""

from __future__ import annotations

from engine import System


class BridgeSystem(System):
    name = "bridge"
    reads = ("ping", "sonar", "clock", "vehicle", "navigation")
    writes = ("bridge",)

    def __init__(self, publish) -> None:
        self.publish = publish           # the dive's own: what the vehicle's sensors report

    def step(self, world) -> None:
        bridge = world.bridge
        if bridge is None:
            return
        # A vehicle whose sonar our own controller can read and a customer's
        # cannot is the wrong way round: ours is the reference and theirs is
        # the product.
        if world.ping.fresh and world.sonar is not None:
            fan = world.sonar.fan()
            bridge.publish_sonar(fan["bearingsRad"], fan["rangesM"], world.sonar.near, world.sonar.far)
        if world.clock.taken % 10 == 0:
            self.publish()


class RecordSystem(System):
    name = "record"
    reads = ("swath", "clock", "vehicle", "task", "thrust", "power", "contacts", "navigation", "bridge")
    writes = ("record",)

    # How often the dive's state goes on its log. One a second put four hundred
    # lines on a five-minute run's record that nobody reads one by one; the
    # console gets twenty a second over its own channel regardless.
    REPORT_EVERY_S = 5.0

    def __init__(self, dive, say) -> None:
        self.dive = dive                 # what the recorder and the log read
        self.say = say
        self.reported = 0.0

    def step(self, world) -> None:
        recorder = world.record
        swath = world.swath
        if recorder is not None:
            if swath.fresh and swath.value["beams"]:
                recorder.sounded(swath.value)
            recorder.step(self.dive)
        now = world.clock.simulated
        if now - self.reported >= self.REPORT_EVERY_S:
            self.reported = now
            self.say("state", **self.dive.state())
