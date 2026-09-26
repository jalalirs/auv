"""Which of a dive's conditions were measured, and which were nobody saying.

The control plane has always known that conditions are either observed at an
instant or constructed by a person, and it refuses the ones whose instant
disagrees with their kind. The runtime read only the numbers. So a dive record
said 1025 kg/m3 whether a CTD had measured it or the default had stood in, and
still water whether the sea was calm or the field was empty. Those are not the
same dive.
"""

import pathlib
import sys


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from hydrodynamics import Allocator, Body, Hydrodynamics
from runner import Dive

PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "catalog/vehicles/bluerov2/dynamics.json"

# A reading as `asMeasured` writes one: the field it became, the instant, and
# the instrument.
BUOY = {"what": "wave height", "parameter": "significantWaveHeightM",
        "at": "2026-09-20T06:00:00Z", "from": "a Sofar Spotter buoy in the water",
        "through": "aqualink.org"}


def came_from(conditions):
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 10, "initialState": {"positionM": [0, 0, -7]},
             "conditions": conditions}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **detail: None)
    return dive.where_conditions_came_from()


def test_conditions_nobody_stated_are_assumed_and_say_what_stood_in():
    told = came_from({"kind": "constructed", "parameters": {}})
    assert told["counted"]["measured"] == 0
    assert told["counted"]["chosen"] == 0
    assert told["fields"]["currentMetresPerSecond"] == {
        "how": "assumed", "instead": "still water"}
    assert told["fields"]["densityKgM3"] == {
        "how": "assumed", "instead": "ordinary seawater"}


def test_a_number_somebody_typed_is_chosen_not_measured():
    told = came_from({"kind": "constructed",
                      "parameters": {"currentMetresPerSecond": 0.4, "visibilityM": 8.0}})
    assert told["fields"]["currentMetresPerSecond"] == {"how": "chosen"}
    assert told["fields"]["visibilityM"] == {"how": "chosen"}
    assert told["counted"]["measured"] == 0


def test_an_observed_reading_carries_its_instrument_and_its_instant():
    told = came_from({"kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
                      "sources": [BUOY],
                      "parameters": {"significantWaveHeightM": 0.4, "waveMeanPeriodS": 6.0}})
    wave = told["fields"]["significantWaveHeightM"]
    assert wave["how"] == "measured"
    assert wave["at"] == "2026-09-20T06:00:00Z"
    assert wave["from"] == "a Sofar Spotter buoy in the water"
    # Measured all the same, with the instant off the set, when no source
    # named the field — which is how every record written before this reads.
    assert told["fields"]["waveMeanPeriodS"] == {"how": "measured", "at": "2026-09-20T06:00:00Z"}


def test_nothing_measures_a_current_so_an_observed_set_still_chose_it():
    told = came_from({"kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
                      "parameters": {"currentMetresPerSecond": 0.3, "currentHeadingDeg": 90.0,
                                     "currentNotMeasured": True,
                                     "significantWaveHeightM": 0.4}})
    assert told["fields"]["currentMetresPerSecond"] == {"how": "chosen"}
    assert told["fields"]["currentHeadingDeg"] == {"how": "chosen"}
    assert told["fields"]["significantWaveHeightM"]["how"] == "measured"


def test_density_worked_out_of_a_ctd_is_derived_and_not_measured():
    told = came_from({"kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
                      "parameters": {"salinityPsu": 40.6, "temperatureC": 26.0}})
    assert told["fields"]["densityKgM3"] == {
        "how": "derived", "fromFields": ["salinityPsu", "temperatureC"],
        "by": "the equation of state"}
    assert told["fields"]["salinityPsu"]["how"] == "measured"


def test_a_density_somebody_measured_outright_is_not_derived():
    told = came_from({"kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
                      "parameters": {"densityKgM3": 1029.0, "salinityPsu": 40.6,
                                     "temperatureC": 26.0}})
    assert told["fields"]["densityKgM3"]["how"] == "measured"


def test_an_empty_field_is_not_a_statement():
    told = came_from({"kind": "constructed",
                      "parameters": {"visibilityM": "", "waterType": None}})
    assert told["fields"]["visibilityM"]["how"] == "assumed"
    assert told["fields"]["waterType"]["how"] == "assumed"


def test_every_field_is_counted_exactly_once():
    told = came_from({"kind": "observed", "observedAt": "2026-09-20T06:00:00Z",
                      "sources": [BUOY],
                      "parameters": {"significantWaveHeightM": 0.4, "salinityPsu": 40.6,
                                     "temperatureC": 26.0, "currentNotMeasured": True}})
    assert sum(told["counted"].values()) == len(told["fields"])


def test_a_dive_reports_where_its_conditions_came_from():
    """Not only available — actually in what the run hands back."""
    model = Hydrodynamics.from_package(PACKAGE)
    brief = {"durationSeconds": 10, "initialState": {"positionM": [0, 0, -7]},
             "conditions": {"kind": "constructed", "parameters": {"visibilityM": 8.0}}}
    dive = Dive(brief, Body(model), Allocator(model), pathlib.Path("nowhere.usda"),
                lambda kind, **detail: None)
    said = dive.conditions_said()
    assert said["cameFrom"]["fields"]["visibilityM"] == {"how": "chosen"}
