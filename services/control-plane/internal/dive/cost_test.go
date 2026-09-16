package dive

import (
	"math"
	"strings"
	"testing"
)

// Cost is measured on what worked.
//
// Averaging a dive abandoned at eight minutes with one that ran its full forty
// gives a number that is neither, and it flatters: the failures are the cheap
// ones. On the sweep this was written for, the survivors cost 6 Wh and took
// thirteen minutes while the failures burned the full forty — an average over
// all eight would have priced a thirteen-minute job at half an hour.
func TestPricedOnWhatWorked(t *testing.T) {
	spent := []Spent{}
	for i := 0; i < 2; i++ {
		spent = append(spent, Spent{EnergyWh: 6, Seconds: 780,
			CapacityWh: 266.4, Reserve: 0.1, Survived: true})
	}
	for i := 0; i < 6; i++ {
		spent = append(spent, Spent{EnergyWh: 20, Seconds: 2400,
			CapacityWh: 266.4, Reserve: 0.1, Survived: false})
	}
	got := WhatItCosts(spent, true)
	if math.Abs(got.EnergyWh-6) > 0.01 {
		t.Errorf("a day's work costs what a day's work costs, got %.2f Wh", got.EnergyWh)
	}
	if math.Abs(got.Hours-780.0/3600.0) > 0.001 {
		t.Errorf("the failures are not the job, got %.3f h", got.Hours)
	}
	if got.Survived != 2 || got.Runs != 8 {
		t.Errorf("counted %d of %d", got.Survived, got.Runs)
	}
	if math.Abs(got.Survives-0.25) > 1e-9 || math.Abs(got.ShipDays-4) > 1e-9 {
		t.Errorf("two in eight is four days of ship time for one of work, got %.2f",
			got.ShipDays)
	}
}

// The reserve is not yours.
func TestTheReserveIsNotSpendable(t *testing.T) {
	got := WhatItCosts([]Spent{{EnergyWh: 24, Seconds: 600,
		CapacityWh: 100, Reserve: 0.1, Survived: true}}, true)
	if math.Abs(got.UsableWh-90) > 1e-9 {
		t.Fatalf("ninety of a hundred is spendable, got %.1f", got.UsableWh)
	}
	if math.Abs(got.PerCharge-90.0/24.0) > 1e-9 {
		t.Fatalf("three and three quarters of these on a charge, got %.2f", got.PerCharge)
	}
}

// Which cap binds decides what to buy: a job held back by the battery is fixed
// by a second battery, and a job held back by the clock is not.
func TestWhatHoldsTheDayBack(t *testing.T) {
	// Short and thirsty: the battery runs out before the day does.
	thirsty := WhatItCosts([]Spent{{EnergyWh: 50, Seconds: 600,
		CapacityWh: 200, Reserve: 0.0, Survived: true}}, true)
	if thirsty.HeldBackBy != "the battery" {
		t.Errorf("four on a charge against forty-eight in a day: %q", thirsty.HeldBackBy)
	}
	if math.Abs(thirsty.PerDay-4) > 1e-9 {
		t.Errorf("four a day, got %.2f", thirsty.PerDay)
	}
	// Long and frugal: the day runs out first.
	slow := WhatItCosts([]Spent{{EnergyWh: 5, Seconds: 7200,
		CapacityWh: 200, Reserve: 0.0, Survived: true}}, true)
	if slow.HeldBackBy != "the clock" {
		t.Errorf("four in a day against forty on a charge: %q", slow.HeldBackBy)
	}
	if math.Abs(slow.PerDay-4) > 1e-9 {
		t.Errorf("four a day, got %.2f", slow.PerDay)
	}
}

// Nothing worked, so there is nothing to price — said, rather than answered
// with the cost of the failures.
func TestNothingWorkedIsSaid(t *testing.T) {
	got := WhatItCosts([]Spent{{EnergyWh: 20, Seconds: 2400,
		CapacityWh: 266.4, Reserve: 0.1, Survived: false}}, true)
	if !got.NotEnough || got.EnergyWh != 0 || got.Says != "" {
		t.Fatalf("it priced a job nothing did: %+v", got)
	}
}

// A run with no battery in its package has no cost to state, and is left out
// rather than counted as free.
func TestARunWithNoBatteryIsLeftOut(t *testing.T) {
	if _, ok := SpentOn([]byte(`{"seconds": 600, "task": {"energyWh": 3}}`), true); ok {
		t.Fatal("a dive with no battery was priced as though it had one")
	}
	if _, ok := SpentOn([]byte(`{"seconds": 600, "task": {"energyWh": 3},
	                             "battery": {"capacityWh": 266.4, "reserveFraction": 0.1}}`), true); !ok {
		t.Fatal("a dive with a battery was left out")
	}
}

// The worst case is the ninetieth percentile, not the single worst dive
// anybody ever flew — which would be a plan sized by one bad seed.
func TestWorstIsNotTheOneBadSeed(t *testing.T) {
	spent := []Spent{}
	for i := 0; i < 9; i++ {
		spent = append(spent, Spent{EnergyWh: 10, Seconds: 600,
			CapacityWh: 100, Reserve: 0, Survived: true})
	}
	spent = append(spent, Spent{EnergyWh: 90, Seconds: 600,
		CapacityWh: 100, Reserve: 0, Survived: true})
	got := WhatItCosts(spent, true)
	if got.WorstEnergyWh > 11 {
		t.Fatalf("one bad seed set the size of the plan: %.1f Wh", got.WorstEnergyWh)
	}
}

// Only a sweep can turn a survival rate into days of ship time.
//
// A sweep flies a stated list of doubts once each, so the share that survived
// is a statement about that list. A mission's own past runs are whatever
// happened to be flown, which is not a sample of anything — and dividing by it
// would produce a number that looks like a forecast.
func TestOnlyASweepSpeaksOfShipDays(t *testing.T) {
	spent := []Spent{
		{EnergyWh: 6, Seconds: 780, CapacityWh: 266.4, Reserve: 0.1, Survived: true},
		{EnergyWh: 20, Seconds: 2400, CapacityWh: 266.4, Reserve: 0.1, Survived: false},
	}
	swept := WhatItCosts(spent, true)
	if swept.ShipDays == 0 || !strings.Contains(swept.Says, "ship time") {
		t.Errorf("a sweep should say what the weather costs: %q", swept.Says)
	}
	history := WhatItCosts(spent, false)
	if history.ShipDays != 0 || strings.Contains(history.Says, "ship time") {
		t.Errorf("a mission's history is not a forecast: %q", history.Says)
	}
	if !strings.Contains(history.Says, "working day") {
		t.Errorf("but it still says what a day of it holds: %q", history.Says)
	}
}

// A day pays for the transit, not only for the work.
//
// The cost said "fifty-three runs a day" from the work's own clock, which for
// a survey that works for twelve minutes and swims for eight is a fifth more
// runs than anybody gets. Ship time is the scarce thing this platform exists
// to plan, so a number that is optimistic by a fifth is a number that puts a
// programme a day over.
func TestADayPaysForGettingThereAndBack(t *testing.T) {
	// Twelve minutes of work inside a twenty-minute dive, twice.
	spent := []Spent{
		{Survived: true, Seconds: 720, EnergyWh: 6.0,
			DiveSeconds: 1200, DiveEnergyWh: 9.5,
			CapacityWh: 266.4, Reserve: 0.1},
		{Survived: true, Seconds: 720, EnergyWh: 6.0,
			DiveSeconds: 1200, DiveEnergyWh: 9.5,
			CapacityWh: 266.4, Reserve: 0.1},
	}
	cost := WhatItCosts(spent, false)

	// The work is still priced as the work.
	if math.Abs(cost.Hours-0.2) > 0.001 || math.Abs(cost.EnergyWh-6.0) > 0.001 {
		t.Fatalf("the work should still cost what the work costs: %.3f h, %.2f Wh",
			cost.Hours, cost.EnergyWh)
	}
	// And the dive is longer than the work, which is the whole point.
	if math.Abs(cost.DiveHours-(1200.0/3600.0)) > 0.001 {
		t.Fatalf("the dive is twenty minutes, got %.3f h", cost.DiveHours)
	}
	if math.Abs(cost.WorkingShare-0.6) > 0.01 {
		t.Fatalf("three fifths of this dive is work, got %.2f", cost.WorkingShare)
	}
	// A day divided by the dive, not by the work: twenty-four, not forty.
	if cost.PerDay < 23.0 || cost.PerDay > 25.0 {
		t.Fatalf("eight hours of twenty-minute dives is about twenty-four, got %.1f",
			cost.PerDay)
	}
}

// And a run that says nothing about the whole dive is not punished for it.
func TestTheWorkStandsInWhenNothingElseIsKnown(t *testing.T) {
	cost := WhatItCosts([]Spent{
		{Survived: true, Seconds: 600, EnergyWh: 5.0, CapacityWh: 266.4, Reserve: 0.1},
	}, false)
	if math.Abs(cost.DiveHours-cost.Hours) > 0.0001 {
		t.Fatalf("with nothing else known the dive is the work: %.3f vs %.3f",
			cost.DiveHours, cost.Hours)
	}
}
