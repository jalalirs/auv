package dive

import (
	"math"
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
	got := WhatItCosts(spent)
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
		CapacityWh: 100, Reserve: 0.1, Survived: true}})
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
		CapacityWh: 200, Reserve: 0.0, Survived: true}})
	if thirsty.HeldBackBy != "the battery" {
		t.Errorf("four on a charge against forty-eight in a day: %q", thirsty.HeldBackBy)
	}
	if math.Abs(thirsty.PerDay-4) > 1e-9 {
		t.Errorf("four a day, got %.2f", thirsty.PerDay)
	}
	// Long and frugal: the day runs out first.
	slow := WhatItCosts([]Spent{{EnergyWh: 5, Seconds: 7200,
		CapacityWh: 200, Reserve: 0.0, Survived: true}})
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
		CapacityWh: 266.4, Reserve: 0.1, Survived: false}})
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
	got := WhatItCosts(spent)
	if got.WorstEnergyWh > 11 {
		t.Fatalf("one bad seed set the size of the plan: %.1f Wh", got.WorstEnergyWh)
	}
}
