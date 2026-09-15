// What it will cost.
//
// Every input has been in the record for weeks and nobody has asked it for
// anything. A dive knows its energy to a hundredth of a watt-hour and the
// battery knows its capacity and the reserve it keeps back, so dives per
// charge is arithmetic. A dive knows how long it took, so dives per working
// day is arithmetic. A sweep knows what share of its scenarios survived, and
// that is the share of days the weather gives you.
//
// This is the step that turns "survives 2 of 8" into a sentence somebody can
// take to whoever signs the ship time.
//
// Two rules it keeps, because the arithmetic is easy and being wrong about it
// is expensive:
//
//   **Cost is measured on what worked.** Averaging the energy of a dive that
//   was abandoned at eight minutes with one that ran its full forty gives a
//   number that is neither, and it flatters: the failures are cheap. A day's
//   work is the cost of a day's work.
//
//   **The reserve is not yours.** A battery's usable energy is its capacity
//   less the reserve it is required to keep, and a plan that spends into the
//   reserve is a plan that surfaces a vehicle on a beach.

package dive

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"sort"
)

// AWorkingDay is how long a day of ship time is, in hours.
//
// Eight, because that is a working day at sea for the people who launch and
// recover, and the number that matters is how many of *those* a job takes. It
// is stated rather than derived so that whoever disagrees can see what they
// are disagreeing with.
const AWorkingDay = 8.0

// Spent is what one run cost.
type Spent struct {
	EnergyWh   float64
	Seconds    float64
	CapacityWh float64
	Reserve    float64
	Survived   bool
}

// Cost is what a piece of work takes, and what the weather adds.
type Cost struct {
	// How many runs this was read from, and how many of them did the job.
	Runs     int `json:"runs"`
	Survived int `json:"survived"`

	// What one run of it costs. Measured on the runs that did the job: a dive
	// abandoned at eight minutes is cheap and is not what a day's work costs.
	EnergyWh      float64 `json:"energyWh"`
	WorstEnergyWh float64 `json:"worstEnergyWh"`
	Hours         float64 `json:"hours"`
	WorstHours    float64 `json:"worstHours"`

	// What the vehicle has to spend, and therefore how many of these fit on a
	// charge. The reserve is not yours.
	CapacityWh      float64 `json:"capacityWh"`
	ReserveFraction float64 `json:"reserveFraction"`
	UsableWh        float64 `json:"usableWh"`
	PerCharge       float64 `json:"perCharge"`

	// How many fit in a working day, and what limits that: the battery or the
	// clock. Saying which is the whole use of the number — a job held back by
	// the battery is fixed by a second battery, and a job held back by the
	// clock is not.
	WorkingDayHours float64 `json:"workingDayHours"`
	PerDay          float64 `json:"perDay"`
	HeldBackBy      string  `json:"heldBackBy,omitempty"`

	// What the weather costs on top: the share of attempts that did the job,
	// and how many days of ship time a day of work therefore takes.
	//
	// Only a sweep can say that. A sweep flies a stated list of doubts once
	// each, so the share that survived is a statement about *that list*; a
	// mission's own past runs are whatever happened to be flown, which is not
	// a sample of anything and must not be turned into days.
	Survives  float64 `json:"survives"`
	ShipDays  float64 `json:"shipDaysPerWorkingDay,omitempty"`
	Says      string  `json:"says,omitempty"`
	NotEnough bool    `json:"notEnough"`
}

// WhatItCosts reads a set of runs and says what the work takes.
//
// `doubted` says whether the runs are a sweep's stated list of doubts, flown
// once each, or merely what happened to be flown. Only the first can be turned
// into days of ship time: a mission's own history is not a sample of anything,
// and dividing by it would produce a number that looks like a forecast.
func WhatItCosts(spent []Spent, doubted bool) Cost {
	out := Cost{Runs: len(spent), WorkingDayHours: AWorkingDay}
	worked := []Spent{}
	for _, one := range spent {
		if one.Survived {
			worked = append(worked, one)
		}
	}
	out.Survived = len(worked)
	if len(spent) > 0 {
		out.Survives = float64(len(worked)) / float64(len(spent))
	}
	if len(worked) == 0 {
		// Nothing did the job, so there is nothing to price. Said rather than
		// answered with the cost of the failures, which is the cheap number
		// and the wrong one.
		out.NotEnough = true
		return out
	}

	energies := make([]float64, 0, len(worked))
	hours := make([]float64, 0, len(worked))
	for _, one := range worked {
		energies = append(energies, one.EnergyWh)
		hours = append(hours, one.Seconds/3600.0)
		out.CapacityWh = math.Max(out.CapacityWh, one.CapacityWh)
		out.ReserveFraction = math.Max(out.ReserveFraction, one.Reserve)
	}
	out.EnergyWh = mean(energies)
	out.WorstEnergyWh = worst(energies)
	out.Hours = mean(hours)
	out.WorstHours = worst(hours)

	out.UsableWh = out.CapacityWh * (1.0 - out.ReserveFraction)
	if out.EnergyWh > 0 && out.UsableWh > 0 {
		out.PerCharge = out.UsableWh / out.EnergyWh
	}
	// The clock and the battery each cap the day; the smaller cap is the one
	// that binds, and which of the two it is decides what to buy.
	byClock := math.Inf(1)
	if out.Hours > 0 {
		byClock = AWorkingDay / out.Hours
	}
	byCharge := math.Inf(1)
	if out.PerCharge > 0 {
		byCharge = out.PerCharge
	}
	out.PerDay = math.Min(byClock, byCharge)
	switch {
	case math.IsInf(out.PerDay, 1):
		out.PerDay = 0
	case byCharge < byClock:
		out.HeldBackBy = "the battery"
	default:
		out.HeldBackBy = "the clock"
	}

	// And the weather. A job that works two times in eight needs four days of
	// ship time for every day of work, which is the sentence somebody takes to
	// whoever signs.
	//
	// With its assumption said out loud. A sweep is a cross product and not a
	// forecast: it flies every combination once, so one in four surviving
	// means one in four *of those combinations*, and turning that into days
	// assumes they are equally likely. They are not — nobody thinks a dead
	// Doppler log is as likely as a calm morning — and a sentence that hid
	// that would be a sentence somebody quoted at a funder.
	out.Says = fmt.Sprintf("%s of work in a working day, held back by %s.",
		plural(out.PerDay, "run", "runs"), out.HeldBackBy)
	if doubted && out.Survives > 0 {
		out.ShipDays = 1.0 / out.Survives
		out.Says += fmt.Sprintf(
			" Allow %s of ship time for every day of work, if everything in "+
				"the doubt list is equally likely.",
			plural(out.ShipDays, "day", "days"))
	}
	return out
}

// mean is the ordinary one, on a list that is never empty here.
func mean(of []float64) float64 {
	total := 0.0
	for _, one := range of {
		total += one
	}
	return total / float64(len(of))
}

// worst is the ninetieth percentile rather than the maximum.
//
// A plan sized by the single worst dive anybody ever flew is a plan sized by
// one bad seed. A plan sized by the mean is a plan that runs out of battery
// one day in two.
func worst(of []float64) float64 {
	sorted := append([]float64(nil), of...)
	sort.Float64s(sorted)
	at := int(math.Ceil(0.9*float64(len(sorted)))) - 1
	if at < 0 {
		at = 0
	}
	return sorted[at]
}

// plural writes a number the way somebody would say it: whole when it is
// whole, to one place when it is not, and singular at one.
func plural(how float64, one, many string) string {
	if math.Abs(how-1.0) < 0.05 {
		return "1 " + one
	}
	if math.Abs(how-math.Round(how)) < 0.05 {
		return fmt.Sprintf("%.0f %s", math.Round(how), many)
	}
	return fmt.Sprintf("%.1f %s", how, many)
}

// WhatAMissionCosts prices a mission from every run of it there has ever been.
//
// "Before it is flown" means from the last time somebody flew it, which is the
// only honest source: a plan that has never been in the water has no cost to
// state and says so rather than guessing one from the arithmetic of its stages.
func (s *Store) WhatAMissionCosts(ctx context.Context, missionID string) (Cost, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT r.state, coalesce(r.outcome, '{}'::jsonb)
		  FROM dive.run r
		  JOIN dive.dive d ON d.id = r.dive_id
		  JOIN catalog.version v ON v.id = d.mission_version_id
		 WHERE v.asset_id = $1
		   AND r.state IN ('succeeded', 'failed')`, missionID)
	if err != nil {
		return Cost{}, fmt.Errorf("reading what a mission has cost: %w", err)
	}
	defer rows.Close()
	spent := []Spent{}
	for rows.Next() {
		var state string
		var outcome []byte
		if err := rows.Scan(&state, &outcome); err != nil {
			return Cost{}, err
		}
		// Every version of the plan, because the question is what this piece
		// of work costs and a stage moved five metres did not change that.
		// Whether it *did the job* is the run's own business, and a run that
		// did not finish did not.
		if one, ok := SpentOn(outcome, state == "succeeded" && didTheJob(outcome)); ok {
			spent = append(spent, one)
		}
	}
	if err := rows.Err(); err != nil {
		return Cost{}, err
	}
	// Not doubted: these are whatever has been flown, not a stated list flown
	// once each, so they say what a run costs and nothing about the weather.
	return WhatItCosts(spent, false), nil
}

// didTheJob is whether a run's task ran to its end without failing.
//
// Deliberately not a threshold: a threshold is a sweep's question, and a
// mission being priced on its own is being asked what a day of it costs rather
// than whether it works.
func didTheJob(outcome []byte) bool {
	var said struct {
		Task *struct {
			Done   bool `json:"done"`
			Failed bool `json:"failed"`
		} `json:"task"`
	}
	if err := json.Unmarshal(outcome, &said); err != nil || said.Task == nil {
		return false
	}
	return said.Task.Done && !said.Task.Failed
}

// SpentOn reads what one run cost out of its outcome.
func SpentOn(outcome []byte, survived bool) (Spent, bool) {
	var said struct {
		Seconds float64 `json:"seconds"`
		Task    *struct {
			EnergyWh *float64 `json:"energyWh"`
			Seconds  *float64 `json:"seconds"`
		} `json:"task"`
		Battery *struct {
			CapacityWh      float64 `json:"capacityWh"`
			ReserveFraction float64 `json:"reserveFraction"`
			SpentWh         float64 `json:"spentWh"`
		} `json:"battery"`
	}
	if err := json.Unmarshal(outcome, &said); err != nil {
		return Spent{}, false
	}
	one := Spent{Survived: survived, Seconds: said.Seconds}
	if said.Task != nil && said.Task.Seconds != nil && *said.Task.Seconds > 0 {
		one.Seconds = *said.Task.Seconds
	}
	if said.Battery != nil {
		one.CapacityWh = said.Battery.CapacityWh
		one.Reserve = said.Battery.ReserveFraction
		one.EnergyWh = said.Battery.SpentWh
	}
	// The task's own figure where it has one: it is the energy of the *work*,
	// which is what is being priced, rather than of everything the vehicle did
	// while it happened to be switched on.
	if said.Task != nil && said.Task.EnergyWh != nil {
		one.EnergyWh = *said.Task.EnergyWh
	}
	// A run with no battery in its package has no cost to state. Left out
	// rather than counted as free.
	if one.CapacityWh <= 0 || one.EnergyWh <= 0 || one.Seconds <= 0 {
		return Spent{}, false
	}
	return one, true
}
