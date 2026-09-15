// A sweep: one mission, flown against everything nobody can promise about it.
//
// A dive that works is not the question. Ship time is the scarce thing,
// weather windows close, and a season's outplanting happens or it does not.
// What somebody planning a mission wants to know is not whether it works but
// *what breaks it* — and there is no way to find that out except by going and
// finding out, which this does overnight instead of in March.
//
// Three parts, and they are separate on purpose:
//
//   **The cross product.** Every way the doubts could resolve, as a dive each.
//   Arithmetic, and the only part with an opinion in it is that a doubt may
//   change what was *asked for* and not only the water.
//
//   **The flying.** Nothing new: each scenario is an ordinary dive and an
//   ordinary run, admitted by the ordinary scheduler, and the platform already
//   does batches. What is new is that each run says which scenario it is.
//
//   **The answer.** Ranked by what *changes* the outcome rather than by what
//   was present when things failed. That distinction is the difference between
//   a report somebody acts on and a grid nobody reads.

package dive

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// Sweep is a mission and the list of what nobody can promise about it.
type Sweep struct {
	ID               string          `json:"id"`
	OrgID            string          `json:"orgId"`
	MissionVersionID string          `json:"missionVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	Water            json.RawMessage `json:"water"`
	Name             string          `json:"name"`
	Doubts           json.RawMessage `json:"doubts"`
	Good             float64         `json:"good"`
	// How many times each scenario is flown. A scenario is a sample and not a
	// run: with one run either side of a setting, one unlucky seed *is* fifty
	// per cent, and the answer reports it as a dimension that changes
	// everything.
	Repeats   int       `json:"repeats"`
	CreatedAt time.Time `json:"createdAt"`
	CreatedBy        string          `json:"createdBy"`

	// How it is going, counted from its runs rather than kept on the row: a
	// state that had to be maintained would be a state that could be wrong.
	Scenarios int `json:"scenarios"`
	Flown     int `json:"flown"`
	Flying    int `json:"flying"`
}

// SweepSpec describes one to run.
type SweepSpec struct {
	OrgID            string
	MissionVersionID string
	VehicleVersionID string
	Water            json.RawMessage
	Name             string
	Doubts           json.RawMessage
	Good             float64
	Repeats          int
	QueueID          string
	RuntimeVersion   string
	CreatedBy        string
}

func (s SweepSpec) Validate() error {
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("%w: a sweep has a name", domain.ErrInvalid)
	}
	if s.MissionVersionID == "" {
		return fmt.Errorf("%w: a sweep doubts a mission", domain.ErrInvalid)
	}
	if s.VehicleVersionID == "" {
		return fmt.Errorf("%w: a sweep names the vehicle that is not in doubt", domain.ErrInvalid)
	}
	if len(s.Doubts) == 0 {
		return fmt.Errorf("%w: a sweep is a list of what nobody can promise", domain.ErrInvalid)
	}
	if s.Good <= 0 || s.Good > 1 {
		return fmt.Errorf("%w: what counts as done is a fraction of one", domain.ErrInvalid)
	}
	if s.Repeats < 1 || s.Repeats > 25 {
		return fmt.Errorf("%w: a scenario is flown between one and twenty-five times",
			domain.ErrInvalid)
	}
	return nil
}

// ── the cross product ────────────────────────────────────────────────────────

// A Setting is what one resolution of one doubt does.
//
// Everything in it is water, except `objective`, which changes what was asked
// for. That exception carries its weight: without it every scenario had the
// same two hours to work in, so a mission that was merely slower was
// indistinguishable from one that was impossible, and the only advice the
// answer could ever give was "do not go". The useful answer is "allow twice as
// long", and it could not be reached without this.
type Setting map[string]json.RawMessage

// Scenario is one way the doubts could resolve.
type Scenario struct {
	// Which setting was picked in each dimension. This is what goes on the
	// run, and what the answer is grouped by.
	Chosen map[string]string
	// The water it is flown in, and what is asked of it.
	Water     map[string]json.RawMessage
	Objective map[string]json.RawMessage
}

// Label is how a scenario reads to a person: "current:half a knot · fix:none".
func (s Scenario) Label() string {
	keys := make([]string, 0, len(s.Chosen))
	for key := range s.Chosen {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+":"+s.Chosen[key])
	}
	return strings.Join(parts, " · ")
}

// Combinations is every way the doubts could resolve.
//
// In a stable order — dimensions by name, settings in the order the document
// lists them — because a sweep asked for twice should be the same sweep twice,
// and a map iterated in Go's order is not.
func Combinations(doubts map[string]json.RawMessage, base map[string]json.RawMessage) ([]Scenario, error) {
	dimensions := make([]string, 0, len(doubts))
	for name := range doubts {
		dimensions = append(dimensions, name)
	}
	sort.Strings(dimensions)

	// The settings of each dimension, in the order the document lists them.
	settings := make([][]string, len(dimensions))
	values := make([]map[string]Setting, len(dimensions))
	for i, name := range dimensions {
		order, err := keysInOrder(doubts[name])
		if err != nil {
			return nil, fmt.Errorf("%w: the doubt %q is not a list of settings", domain.ErrInvalid, name)
		}
		var said map[string]Setting
		if err := json.Unmarshal(doubts[name], &said); err != nil {
			return nil, fmt.Errorf("%w: the doubt %q is not a list of settings", domain.ErrInvalid, name)
		}
		if len(order) == 0 {
			return nil, fmt.Errorf("%w: the doubt %q has nothing to resolve to", domain.ErrInvalid, name)
		}
		settings[i], values[i] = order, said
	}

	out := []Scenario{}
	picked := make([]int, len(dimensions))
	for {
		one := Scenario{
			Chosen:    map[string]string{},
			Water:     map[string]json.RawMessage{},
			Objective: map[string]json.RawMessage{},
		}
		for key, value := range base {
			one.Water[key] = value
		}
		for i, name := range dimensions {
			which := settings[i][picked[i]]
			one.Chosen[name] = which
			apply(values[i][which], &one)
		}
		out = append(out, one)

		// The odometer.
		at := len(dimensions) - 1
		for at >= 0 {
			picked[at]++
			if picked[at] < len(settings[at]) {
				break
			}
			picked[at] = 0
			at--
		}
		if at < 0 || len(dimensions) == 0 {
			break
		}
	}
	return out, nil
}

// apply puts one setting into a scenario.
func apply(said Setting, into *Scenario) {
	for key, value := range said {
		switch key {
		case "objective":
			var changes map[string]json.RawMessage
			if json.Unmarshal(value, &changes) == nil {
				for name, one := range changes {
					into.Objective[name] = one
				}
			}
		case "failures":
			// Failures accumulate rather than replace: two things going wrong
			// on one dive is the case worth flying, not the case to drop
			// because two dimensions both wanted the same key.
			into.Water["failures"] = mergeArrays(into.Water["failures"], value)
		case "fitted":
			into.Water["fitted"] = mergeObjects(into.Water["fitted"], value)
		default:
			into.Water[key] = value
		}
	}
}

func mergeArrays(was, add json.RawMessage) json.RawMessage {
	var a, b []json.RawMessage
	_ = json.Unmarshal(was, &a)
	_ = json.Unmarshal(add, &b)
	joined, err := json.Marshal(append(a, b...))
	if err != nil {
		return add
	}
	return joined
}

func mergeObjects(was, add json.RawMessage) json.RawMessage {
	joined := map[string]json.RawMessage{}
	_ = json.Unmarshal(was, &joined)
	var more map[string]json.RawMessage
	_ = json.Unmarshal(add, &more)
	for key, value := range more {
		joined[key] = value
	}
	encoded, err := json.Marshal(joined)
	if err != nil {
		return add
	}
	return encoded
}

// keysInOrder reads an object's keys in the order the document writes them.
//
// Go's maps do not keep it and a sweep's scenarios should read in the order
// somebody wrote their doubts — "still, gentle, half a knot, one knot" rather
// than whatever the hash happened to give.
func keysInOrder(raw json.RawMessage) ([]string, error) {
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	if delimiter, ok := token.(json.Delim); !ok || delimiter != '{' {
		return nil, fmt.Errorf("not an object")
	}
	out := []string{}
	for decoder.More() {
		key, err := decoder.Token()
		if err != nil {
			return nil, err
		}
		name, ok := key.(string)
		if !ok {
			return nil, fmt.Errorf("not a key")
		}
		out = append(out, name)
		var skip json.RawMessage
		if err := decoder.Decode(&skip); err != nil {
			return nil, err
		}
	}
	return out, nil
}

// ── the answer ───────────────────────────────────────────────────────────────

// Flown is one run of one scenario, and how it went.
type Flown struct {
	RunID     string            `json:"runId"`
	DiveID    string            `json:"diveId"`
	Chosen    map[string]string `json:"chosen"`
	Label     string            `json:"label"`
	State     string            `json:"state"`
	Score     float64           `json:"score"`
	Survived  bool              `json:"survived"`
	Ended     string            `json:"ended,omitempty"`
	Says      string            `json:"says,omitempty"`
	HeldBack  bool              `json:"heldBack"`
	DriftM    *float64          `json:"driftM,omitempty"`
	PhysicsAt *int              `json:"physicsVersion,omitempty"`
}

// Rate is how one setting of one dimension fared.
type Rate struct {
	Value    string  `json:"value"`
	Survived int     `json:"survived"`
	Of       int     `json:"of"`
	Share    float64 `json:"failedShare"`
}

// Dimension is one doubt and what it did to the outcome.
type Dimension struct {
	Name string `json:"name"`
	// How much this changes the outcome: the gap between its best setting and
	// its worst. A dimension whose settings all fail equally is telling you it
	// does not matter.
	Changes float64 `json:"changes"`
	Rates   []Rate  `json:"rates"`
}

// Findings is what the sweep is for.
type Findings struct {
	Scenarios int     `json:"scenarios"`
	Flown     int     `json:"flown"`
	FlownRuns int     `json:"flownRuns"`
	Flying    int     `json:"flying"`
	Survived  int     `json:"survived"`
	Repeats   int     `json:"repeats"`
	Good      float64 `json:"good"`

	// Ranked by how much each *changes* the outcome, not by how often it was
	// present when the mission failed. Those are different and the second is
	// misleading: in a sweep where the current is what kills you, half the
	// failures also happen to be in murky water and half in clear, and listing
	// both at fifty per cent invites somebody to go and worry about visibility.
	Matters []Dimension `json:"matters"`
	// Named once, quietly, and not ranked.
	MadeNoDifference []string `json:"madeNoDifference"`

	// The sentence a dive plan actually turns on.
	TurnsOn   string `json:"turnsOn,omitempty"`
	At        string `json:"at,omitempty"`
	FailsOf   [2]int `json:"failsOf,omitempty"`
	Rescue    string `json:"rescue,omitempty"`
	RescueOf  [2]int `json:"rescueOf,omitempty"`
	NoRescue  bool   `json:"noRescue"`
	HeldBack  int    `json:"heldBack"`
	// What computed them. A sweep whose runs were not all computed by the same
	// simulator is a table that should not be one, and saying so here is the
	// same rule the record keeps everywhere else.
	Physics []int `json:"physics"`

	// What the work costs, and what the weather costs on top. Priced on the
	// scenarios that did the job: a day's work is the cost of a day's work,
	// and the failures are the cheap ones.
	Cost Cost `json:"cost"`

	// Every question asked, with how many times it was asked and how it went.
	// This is what the answer above is about; the runs are underneath it.
	Scenarios_ []ScenarioFlown `json:"scenariosFlown"`
	Runs       []Flown         `json:"runs"`
}

// MATTERS is the gap, between a dimension's best setting and its worst, at
// which it stops being noise and starts being the answer. Fifteen points:
// below that, in a sweep of this size, the difference is as likely to be which
// seeds were drawn as which setting was flown.
const MATTERS = 0.15

// Scenario is how a scenario went across every run of it.
//
// A scenario is a sample and not a run. With one run either side of a setting
// an unlucky seed *is* fifty per cent, and the answer reports it as a
// dimension that changes everything: the sweep that proved this had the same
// water and twice the allowance score 0.971 and then 0.429, because the
// vehicle was dead reckoning for forty minutes and one seed drifted where the
// other did not.
//
// So: it survives when more than half its runs did, and its score is the
// median of them. The spread is kept, because a scenario that worked twice in
// three is a different thing from one that worked three times in three, and
// somebody planning ship time should be able to see which they have.
type ScenarioFlown struct {
	Label    string            `json:"label"`
	Chosen   map[string]string `json:"chosen"`
	Runs     int               `json:"runs"`
	Survived int               `json:"survivedRuns"`
	Works    bool              `json:"survived"`
	Score    float64           `json:"score"`
	Worst    float64           `json:"worst"`
	Best     float64           `json:"best"`
	Says     string            `json:"says,omitempty"`
	HeldBack bool              `json:"heldBack"`
}

// gather turns runs into scenarios, keeping the order they were first seen.
func gather(flown []Flown) []ScenarioFlown {
	// Keyed on what was chosen rather than on the label a run happens to
	// carry: the settings *are* the scenario and the label is a rendering of
	// them, so grouping by the rendering would put every run of a sweep in one
	// bucket the first time somebody forgot to fill it in.
	order := []string{}
	at := map[string][]Flown{}
	for _, one := range flown {
		key := Scenario{Chosen: one.Chosen}.Label()
		if _, seen := at[key]; !seen {
			order = append(order, key)
		}
		at[key] = append(at[key], one)
	}
	out := make([]ScenarioFlown, 0, len(order))
	for _, label := range order {
		runs := at[label]
		scores := make([]float64, 0, len(runs))
		one := ScenarioFlown{Label: label, Chosen: runs[0].Chosen, Runs: len(runs)}
		for _, run := range runs {
			scores = append(scores, run.Score)
			if run.Survived {
				one.Survived++
			}
			if run.HeldBack {
				one.HeldBack = true
			}
			if one.Says == "" {
				one.Says = run.Says
			}
		}
		sort.Float64s(scores)
		one.Worst, one.Best = scores[0], scores[len(scores)-1]
		one.Score = median(scores)
		// More than half. At one run this is that run, which is what every
		// sweep flown before this did.
		one.Works = one.Survived*2 > len(runs)
		out = append(out, one)
	}
	return out
}

func median(sorted []float64) float64 {
	n := len(sorted)
	if n%2 == 1 {
		return sorted[n/2]
	}
	return (sorted[n/2-1] + sorted[n/2]) / 2.0
}

// What is the answer: what breaks the mission, and what would fix it.
func What(flown []Flown, good float64) Findings {
	// Every question asked, each with every time it was asked. What is judged
	// from here on is the scenario, because that is what a doubt resolves to;
	// the runs are how confidently it is known.
	scenarios := gather(flown)
	out := Findings{Good: good, Flown: len(scenarios), FlownRuns: len(flown),
		Matters: []Dimension{}, MadeNoDifference: []string{},
		Scenarios_: scenarios, Runs: flown, Physics: []int{}}
	seen := map[int]bool{}
	for _, one := range scenarios {
		if one.Works {
			out.Survived++
		}
		if one.HeldBack && !one.Works {
			out.HeldBack++
		}
	}
	for _, one := range flown {
		if one.PhysicsAt != nil && !seen[*one.PhysicsAt] {
			seen[*one.PhysicsAt] = true
			out.Physics = append(out.Physics, *one.PhysicsAt)
		}
	}
	sort.Ints(out.Physics)
	if len(scenarios) == 0 {
		return out
	}

	names := map[string]bool{}
	for _, one := range scenarios {
		for name := range one.Chosen {
			names[name] = true
		}
	}
	dimensions := make([]string, 0, len(names))
	for name := range names {
		dimensions = append(dimensions, name)
	}
	sort.Strings(dimensions)

	for _, name := range dimensions {
		rates := ratesOf(scenarios, name)
		if len(rates) == 0 {
			continue
		}
		worst, best := rates[0].Share, rates[0].Share
		for _, one := range rates {
			worst = math.Max(worst, one.Share)
			best = math.Min(best, one.Share)
		}
		changes := worst - best
		if changes >= MATTERS {
			out.Matters = append(out.Matters, Dimension{Name: name, Changes: changes, Rates: rates})
		} else {
			out.MadeNoDifference = append(out.MadeNoDifference, name)
		}
	}
	// Worst first: the thing to read is the thing that changes most. Ties by
	// name, so that two doubts which change the outcome by exactly as much as
	// each other come out in the same order every time — and so that the same
	// sweep read twice reads the same, which matters more than which of two
	// equal answers is on top.
	sort.SliceStable(out.Matters, func(a, b int) bool {
		if out.Matters[a].Changes != out.Matters[b].Changes {
			return out.Matters[a].Changes > out.Matters[b].Changes
		}
		return out.Matters[a].Name < out.Matters[b].Name
	})
	if len(out.Matters) == 0 || out.Survived == len(scenarios) {
		return out
	}

	// The worst single setting, and whether anything else recovers it.
	turns := out.Matters[0]
	at := turns.Rates[0] // ratesOf sorts worst first
	out.TurnsOn, out.At = turns.Name, at.Value
	out.FailsOf = [2]int{at.Of - at.Survived, at.Of}

	doomed := []ScenarioFlown{}
	for _, one := range scenarios {
		if one.Chosen[turns.Name] == at.Value {
			doomed = append(doomed, one)
		}
	}
	bestSaved, bestOf, bestName, bestValue := 0, 0, "", ""
	bestShare := -1.0
	for _, other := range dimensions {
		if other == turns.Name {
			continue
		}
		for _, one := range ratesOf(doomed, other) {
			share := float64(one.Survived) / float64(one.Of)
			if share > bestShare {
				bestShare, bestSaved, bestOf, bestName, bestValue =
					share, one.Survived, one.Of, other, one.Value
			}
		}
	}
	if bestSaved > 0 {
		out.Rescue = bestName + " to " + bestValue
		out.RescueOf = [2]int{bestSaved, bestOf}
	} else {
		out.NoRescue = true
	}
	return out
}

// ratesOf is how each setting of one dimension fared, worst first. Counted in
// scenarios rather than runs: the question is how many of the situations this
// setting appears in still work.
func ratesOf(flown []ScenarioFlown, dimension string) []Rate {
	order := []string{}
	at := map[string]*Rate{}
	for _, one := range flown {
		value, said := one.Chosen[dimension]
		if !said {
			continue
		}
		if at[value] == nil {
			at[value] = &Rate{Value: value}
			order = append(order, value)
		}
		at[value].Of++
		if one.Works {
			at[value].Survived++
		}
	}
	sort.Strings(order)
	out := make([]Rate, 0, len(order))
	for _, value := range order {
		one := at[value]
		one.Share = float64(one.Of-one.Survived) / float64(one.Of)
		out = append(out, *one)
	}
	// Worst first, and by name within a tie so the order does not wander.
	sort.SliceStable(out, func(a, b int) bool {
		if out[a].Share != out[b].Share {
			return out[a].Share > out[b].Share
		}
		return out[a].Value < out[b].Value
	})
	return out
}

// ── keeping one ──────────────────────────────────────────────────────────────

const selectSweep = `
	SELECT id, org_id, mission_version_id, vehicle_version_id, water, name,
	       doubts, good, repeats, created_at, created_by
	  FROM dive.sweep`

func scanSweep(row interface{ Scan(...any) error }) (Sweep, error) {
	var one Sweep
	err := row.Scan(&one.ID, &one.OrgID, &one.MissionVersionID, &one.VehicleVersionID,
		&one.Water, &one.Name, &one.Doubts, &one.Good, &one.Repeats,
		&one.CreatedAt, &one.CreatedBy)
	return one, err
}

// CreateSweep records a sweep and asks for every scenario in it.
//
// One transaction: a sweep whose dives were half created would be a sweep
// nobody could read and nobody could finish, and there is no reason to allow
// one to exist.
func (s *Store) CreateSweep(ctx context.Context, conn db.Conn, spec SweepSpec) (Sweep, error) {
	if err := spec.Validate(); err != nil {
		return Sweep{}, err
	}
	var doubts map[string]json.RawMessage
	if err := json.Unmarshal(spec.Doubts, &doubts); err != nil {
		return Sweep{}, fmt.Errorf("%w: the doubts are not a list of dimensions", domain.ErrInvalid)
	}
	base := map[string]json.RawMessage{}
	if len(spec.Water) > 0 {
		if err := json.Unmarshal(spec.Water, &base); err != nil {
			return Sweep{}, fmt.Errorf("%w: the water is not a set of parameters", domain.ErrInvalid)
		}
	}
	scenarios, err := Combinations(doubts, base)
	if err != nil {
		return Sweep{}, err
	}

	id := ids.New(ids.KindSweep)
	if _, err := conn.Exec(ctx, `
		INSERT INTO dive.sweep (id, org_id, mission_version_id, vehicle_version_id,
		                        water, name, doubts, good, repeats, created_by)
		VALUES ($1, $2, $3, $4, coalesce($5, '{}'::jsonb), $6, $7, $8, $9, $10)`,
		id, spec.OrgID, spec.MissionVersionID, spec.VehicleVersionID,
		nullJSON(spec.Water), spec.Name, []byte(spec.Doubts), spec.Good,
		spec.Repeats, spec.CreatedBy); err != nil {
		if db.IsForeignKeyViolation(err) {
			// A caller naming something that is not there. Theirs to fix, and
			// theirs to be told about: the versions are the easy ones to get
			// wrong, because a vehicle and a version of it look alike.
			return Sweep{}, fmt.Errorf(
				"%w: a sweep names a published *version* of a mission and of a "+
					"vehicle, and one of those does not exist", domain.ErrInvalid)
		}
		return Sweep{}, fmt.Errorf("recording a sweep: %w", err)
	}

	for _, one := range scenarios {
		if err := s.askForScenario(ctx, conn, spec, id, one); err != nil {
			return Sweep{}, err
		}
	}
	made, err := scanSweep(conn.QueryRow(ctx, selectSweep+` WHERE id = $1`, id))
	if err != nil {
		return Sweep{}, fmt.Errorf("reading back a sweep: %w", err)
	}
	made.Scenarios = len(scenarios) * spec.Repeats
	return made, nil
}

// askForScenario makes one scenario's water, dive and run.
func (s *Store) askForScenario(ctx context.Context, conn db.Conn, spec SweepSpec,
	sweepID string, one Scenario) error {
	label := one.Label()
	water, err := json.Marshal(one.Water)
	if err != nil {
		return fmt.Errorf("encoding the water for %q: %w", label, err)
	}
	conditions, err := s.CreateConditions(ctx, conn, ConditionsSpec{
		Kind:       Constructed,
		Name:       cut(spec.Name+" ~ "+label, 120),
		Parameters: water,
		OrgID:      &spec.OrgID,
		CreatedBy:  spec.CreatedBy,
	})
	if err != nil {
		return err
	}
	objective, err := json.Marshal(one.Objective)
	if err != nil {
		return fmt.Errorf("encoding what is asked of %q: %w", label, err)
	}
	made, err := s.CreateDive(ctx, conn, DiveSpec{
		OrgID:            spec.OrgID,
		Name:             cut(spec.Name+" ~ "+label, 200),
		MissionVersionID: spec.MissionVersionID,
		VehicleVersionID: spec.VehicleVersionID,
		ConditionsID:     conditions.ID,
		// What this scenario changed about what was asked for, laid over the
		// mission rather than replacing it. Empty for most scenarios, in which
		// case the mission's own stages are flown whole.
		ObjectiveOverlay: overlaid(objective),
		CreatedBy:        spec.CreatedBy,
	})
	if err != nil {
		return err
	}
	chosen, err := json.Marshal(one.Chosen)
	if err != nil {
		return fmt.Errorf("encoding which scenario %q is: %w", label, err)
	}
	// One dive, flown as many times as the sweep asks. Runs of one dive rather
	// than one run of many dives, because they are the same question asked
	// again — and each draws its own seed, which is the whole point.
	for i := 0; i < spec.Repeats; i++ {
		if _, err := s.RequestRun(ctx, conn, RunSpec{
			DiveID:         made.ID,
			QueueID:        spec.QueueID,
			Mode:           Batch,
			RuntimeVersion: spec.RuntimeVersion,
			RequestedBy:    spec.CreatedBy,
			Scenario:       chosen,
			SweepID:        sweepID,
		}); err != nil {
			return fmt.Errorf("asking for %q: %w", label, err)
		}
	}
	return nil
}

// overlaid is a scenario's changes to the objective, or nothing when it made
// none — in which case the mission's own stages are used whole.
func overlaid(said json.RawMessage) json.RawMessage {
	if len(said) == 0 || string(said) == "{}" || string(said) == "null" {
		return nil
	}
	return said
}

func cut(said string, at int) string {
	if len(said) <= at {
		return said
	}
	return said[:at]
}

// Sweep reads one, with how far along it is.
func (s *Store) Sweep(ctx context.Context, id string) (Sweep, error) {
	one, err := scanSweep(s.pool.QueryRow(ctx, selectSweep+` WHERE id = $1`, id))
	if err != nil {
		return Sweep{}, db.Translate(err)
	}
	if err := s.countSweep(ctx, &one); err != nil {
		return Sweep{}, err
	}
	return one, nil
}

// Sweeps lists an institution's, newest first.
func (s *Store) Sweeps(ctx context.Context, orgID string) ([]Sweep, error) {
	rows, err := s.pool.Query(ctx, selectSweep+
		` WHERE org_id = $1 ORDER BY created_at DESC`, orgID)
	if err != nil {
		return nil, fmt.Errorf("listing sweeps: %w", err)
	}
	defer rows.Close()
	found := []Sweep{}
	for rows.Next() {
		one, err := scanSweep(rows)
		if err != nil {
			return nil, err
		}
		found = append(found, one)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for i := range found {
		if err := s.countSweep(ctx, &found[i]); err != nil {
			return nil, err
		}
	}
	return found, nil
}

// countSweep fills in how far along a sweep is, from its runs.
func (s *Store) countSweep(ctx context.Context, one *Sweep) error {
	err := s.pool.QueryRow(ctx, `
		SELECT count(*),
		       count(*) FILTER (WHERE state IN ('succeeded', 'failed', 'cancelled', 'expired')),
		       count(*) FILTER (WHERE state IN ('queued', 'preparing', 'running'))
		  FROM dive.run WHERE sweep_id = $1`, one.ID).
		Scan(&one.Scenarios, &one.Flown, &one.Flying)
	if err != nil {
		return fmt.Errorf("counting a sweep's runs: %w", err)
	}
	return nil
}

// Findings reads a sweep's runs and says what they mean.
func (s *Store) Findings(ctx context.Context, id string) (Findings, error) {
	one, err := s.Sweep(ctx, id)
	if err != nil {
		return Findings{}, err
	}
	rows, err := s.pool.Query(ctx, `
		SELECT r.id, r.dive_id, r.state, coalesce(r.scenario, '{}'::jsonb),
		       coalesce(r.outcome, '{}'::jsonb), r.physics_version
		  FROM dive.run r
		 WHERE r.sweep_id = $1
		   AND r.state IN ('succeeded', 'failed')
		 ORDER BY r.requested_at`, id)
	if err != nil {
		return Findings{}, fmt.Errorf("reading a sweep's runs: %w", err)
	}
	defer rows.Close()

	flown := []Flown{}
	spent := []Spent{}
	for rows.Next() {
		var got Flown
		var chosen, outcome []byte
		if err := rows.Scan(&got.RunID, &got.DiveID, &got.State, &chosen,
			&outcome, &got.PhysicsAt); err != nil {
			return Findings{}, err
		}
		if err := json.Unmarshal(chosen, &got.Chosen); err != nil {
			got.Chosen = map[string]string{}
		}
		got.Label = Scenario{Chosen: got.Chosen}.Label()
		readOutcome(outcome, &got, one.Good)
		if cost, ok := SpentOn(outcome, got.Survived); ok {
			spent = append(spent, cost)
		}
		flown = append(flown, got)
	}
	if err := rows.Err(); err != nil {
		return Findings{}, err
	}
	found := What(flown, one.Good)
	// How many distinct questions were asked, against how many runs that is.
	found.Scenarios = one.Scenarios / max(1, one.Repeats)
	found.Flying = one.Flying
	found.Repeats = one.Repeats
	found.Cost = WhatItCosts(spent, true)
	return found, nil
}

// readOutcome takes what a run said about itself onto the scenario.
func readOutcome(raw []byte, into *Flown, good float64) {
	var said struct {
		Ended string `json:"ended"`
		Task  *struct {
			Score    *float64 `json:"score"`
			Says     string   `json:"says"`
			HeldBack any      `json:"heldBack"`
		} `json:"task"`
		Navigation *struct {
			DriftM *float64 `json:"driftM"`
		} `json:"navigation"`
	}
	if err := json.Unmarshal(raw, &said); err != nil {
		return
	}
	into.Ended = said.Ended
	if said.Navigation != nil {
		into.DriftM = said.Navigation.DriftM
	}
	if said.Task == nil {
		return
	}
	into.Says = said.Task.Says
	into.HeldBack = said.Task.HeldBack != nil
	if said.Task.Score != nil {
		into.Score = *said.Task.Score
	}
	// A run that did not finish did not survive, whatever it scored on the way.
	into.Survived = into.State == "succeeded" && into.Score >= good
}
