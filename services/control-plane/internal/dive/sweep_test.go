package dive

import (
	"encoding/json"
	"testing"
)

// The cross product is every way the doubts could resolve, in a stable order.
func TestCombinations(t *testing.T) {
	doubts := map[string]json.RawMessage{
		"current": json.RawMessage(`{"still": {"currentMetresPerSecond": 0.0},
		                             "half knot": {"currentMetresPerSecond": 0.26}}`),
		"fix": json.RawMessage(`{"array": {"positioning": {"kind": "lbl"}},
		                        "nothing": {"positioning": {"kind": "none"}}}`),
	}
	base := map[string]json.RawMessage{"salinityPsu": json.RawMessage(`40.6`)}
	got, err := Combinations(doubts, base)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 4 {
		t.Fatalf("two doubts of two settings is four scenarios, got %d", len(got))
	}
	labels := map[string]bool{}
	for _, one := range got {
		labels[one.Label()] = true
		if string(one.Water["salinityPsu"]) != "40.6" {
			t.Errorf("%s lost the water that was not in doubt", one.Label())
		}
	}
	for _, want := range []string{
		"current:still · fix:array", "current:still · fix:nothing",
		"current:half knot · fix:array", "current:half knot · fix:nothing"} {
		if !labels[want] {
			t.Errorf("missing scenario %q", want)
		}
	}

	// Asked for twice is the same sweep twice.
	again, _ := Combinations(doubts, base)
	for i := range got {
		if got[i].Label() != again[i].Label() {
			t.Fatalf("the order wandered: %q then %q", got[i].Label(), again[i].Label())
		}
	}
}

// A doubt may change what was asked for, and not only the water.
//
// Without this every scenario has the same working day, so a mission that is
// merely slower is indistinguishable from one that is impossible, and the only
// advice the answer can give is "do not go".
func TestADoubtMayChangeWhatWasAskedFor(t *testing.T) {
	got, err := Combinations(map[string]json.RawMessage{
		"how long": json.RawMessage(`{"a shift": {"objective": {"timeLimitS": 2400}},
		                              "two shifts": {"objective": {"timeLimitS": 4800}}}`),
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 {
		t.Fatalf("wanted two scenarios, got %d", len(got))
	}
	for _, one := range got {
		if len(one.Water) != 0 {
			t.Errorf("%s put a change to the plan in the water", one.Label())
		}
		if string(one.Objective["timeLimitS"]) == "" {
			t.Errorf("%s did not change what was asked for", one.Label())
		}
	}
}

// Two things going wrong on one dive is the case worth flying.
func TestFailuresAccumulate(t *testing.T) {
	got, err := Combinations(map[string]json.RawMessage{
		"thruster": json.RawMessage(`{"gone": {"failures": [{"kind": "thruster"}]}}`),
		"log":      json.RawMessage(`{"gone": {"failures": [{"kind": "dvl"}]}}`),
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	var failures []map[string]any
	if err := json.Unmarshal(got[0].Water["failures"], &failures); err != nil {
		t.Fatal(err)
	}
	if len(failures) != 2 {
		t.Fatalf("both failures should be on the dive, got %d", len(failures))
	}
}

// ── the answer ───────────────────────────────────────────────────────────────

// scenario builds one flown scenario for the tests below.
func flown(survived bool, chosen map[string]string) Flown {
	score := 0.2
	if survived {
		score = 0.95
	}
	return Flown{Chosen: chosen, State: "succeeded", Score: score, Survived: survived}
}

// Ranked by what changes the outcome, not by what was present when it failed.
//
// The current is what kills this mission. Half its failures are also in murky
// water and half in clear, so ranking by presence would list visibility at
// fifty per cent and invite somebody to go and worry about it.
func TestRankedByWhatChangesTheOutcome(t *testing.T) {
	runs := []Flown{}
	for _, current := range []string{"still", "one knot"} {
		for _, clarity := range []string{"clear", "murky"} {
			for i := 0; i < 2; i++ {
				runs = append(runs, flown(current == "still",
					map[string]string{"current": current, "water clarity": clarity}))
			}
		}
	}
	// Four scenarios, flown twice each: two of the four work. Counted in
	// scenarios rather than runs, because a scenario is what a doubt resolves
	// to and the runs are how confidently it is known.
	found := What(runs, 0.8)
	if found.Survived != 2 || found.Flown != 4 || found.FlownRuns != 8 {
		t.Fatalf("two of four scenarios over eight runs, got %d of %d over %d",
			found.Survived, found.Flown, found.FlownRuns)
	}
	if len(found.Matters) != 1 || found.Matters[0].Name != "current" {
		t.Fatalf("the current is what matters, got %v", found.Matters)
	}
	if len(found.MadeNoDifference) != 1 || found.MadeNoDifference[0] != "water clarity" {
		t.Fatalf("clarity made no difference and should be said once, got %v",
			found.MadeNoDifference)
	}
	if found.TurnsOn != "current" || found.At != "one knot" {
		t.Fatalf("it turns on the current at one knot, got %q at %q", found.TurnsOn, found.At)
	}
	if found.FailsOf != [2]int{2, 2} {
		t.Fatalf("both scenarios at one knot fail, got %v", found.FailsOf)
	}
	if !found.NoRescue {
		t.Fatalf("nothing rescues it, so it should say so: %+v", found)
	}
}

// And when something does rescue it, the answer is that change.
func TestTheChangeThatSavesTheMost(t *testing.T) {
	runs := []Flown{}
	for _, current := range []string{"still", "one knot"} {
		for _, fix := range []string{"array", "nothing"} {
			// At one knot it only works with the array.
			ok := current == "still" || fix == "array"
			runs = append(runs, flown(ok, map[string]string{"current": current, "fix": fix}))
		}
	}
	found := What(runs, 0.8)
	if found.TurnsOn != "current" && found.TurnsOn != "fix" {
		t.Fatalf("something should turn it, got %q", found.TurnsOn)
	}
	if found.Rescue == "" {
		t.Fatalf("laying the array rescues it and the answer should say so: %+v", found)
	}
	if found.NoRescue {
		t.Fatal("it said nothing rescues it when something does")
	}
}

// A sweep with nothing wrong says so rather than ranking noise.
func TestNothingBreaksIt(t *testing.T) {
	runs := []Flown{
		flown(true, map[string]string{"current": "still"}),
		flown(true, map[string]string{"current": "one knot"}),
	}
	found := What(runs, 0.8)
	if found.Survived != 2 || found.TurnsOn != "" {
		t.Fatalf("nothing breaks it: %+v", found)
	}
}

// A run that did not finish did not survive, whatever it scored on the way.
func TestAFailedRunDidNotSurvive(t *testing.T) {
	var got Flown
	got.State = "failed"
	readOutcome([]byte(`{"task": {"score": 0.99}}`), &got, 0.8)
	if got.Survived {
		t.Fatal("a run that failed did not survive on a score it never finished")
	}
}

// A scenario is a sample, not a run.
//
// With one run either side of a setting an unlucky seed *is* fifty per cent.
// The sweep that proved it had the same water and twice the allowance score
// 0.971 and then 0.429 — nothing about the allowance caused that; the vehicle
// was dead reckoning for forty minutes and one seed drifted where the other
// did not. Flown three times, that scenario works twice in three and the
// dimension it was blamed on disappears.
func TestAScenarioIsASample(t *testing.T) {
	runs := []Flown{}
	add := func(chosen map[string]string, scores ...float64) {
		for _, score := range scores {
			runs = append(runs, Flown{Chosen: chosen, State: "succeeded",
				Score: score, Survived: score >= 0.8})
		}
	}
	// Still water works, whatever the allowance — but one run of it was
	// unlucky, in the way the real sweep was.
	add(map[string]string{"current": "still", "how long": "a shift"}, 0.97, 0.95, 0.96)
	add(map[string]string{"current": "still", "how long": "two shifts"}, 0.43, 0.95, 0.96)
	// Half a knot does not work, whatever the allowance.
	add(map[string]string{"current": "half knot", "how long": "a shift"}, 0.06, 0.07, 0.05)
	add(map[string]string{"current": "half knot", "how long": "two shifts"}, 0.06, 0.05, 0.07)

	found := What(runs, 0.8)
	if found.Flown != 4 || found.FlownRuns != 12 {
		t.Fatalf("four scenarios of three runs, got %d of %d", found.Flown, found.FlownRuns)
	}
	if found.Survived != 2 {
		t.Fatalf("both still-water scenarios work, got %d", found.Survived)
	}
	if len(found.Matters) != 1 || found.Matters[0].Name != "current" {
		t.Fatalf("only the current matters, got %v", found.Matters)
	}
	if len(found.MadeNoDifference) != 1 || found.MadeNoDifference[0] != "how long" {
		t.Fatalf("the allowance made no difference and should say so, got %v",
			found.MadeNoDifference)
	}
	// And the unlucky run is still visible, because a scenario that worked
	// twice in three is a different thing from one that worked three times.
	var marginal *ScenarioFlown
	for i, one := range found.Scenarios_ {
		if one.Chosen["how long"] == "two shifts" && one.Chosen["current"] == "still" {
			marginal = &found.Scenarios_[i]
		}
	}
	if marginal == nil || marginal.Survived != 2 || marginal.Runs != 3 {
		t.Fatalf("the marginal scenario should say it worked twice in three: %+v", marginal)
	}
	if marginal.Worst > 0.5 || marginal.Best < 0.9 {
		t.Fatalf("and keep its spread: %+v", marginal)
	}
}

// One run each is what every sweep flown before this did, and it still works.
func TestOneRunEachIsUnchanged(t *testing.T) {
	runs := []Flown{
		{Chosen: map[string]string{"current": "still"}, State: "succeeded", Score: 0.95, Survived: true},
		{Chosen: map[string]string{"current": "one knot"}, State: "succeeded", Score: 0.2},
	}
	found := What(runs, 0.8)
	if found.Flown != 2 || found.Survived != 1 {
		t.Fatalf("one of two, got %d of %d", found.Survived, found.Flown)
	}
	if found.TurnsOn != "current" || found.At != "one knot" {
		t.Fatalf("it still turns on the current: %q at %q", found.TurnsOn, found.At)
	}
}
