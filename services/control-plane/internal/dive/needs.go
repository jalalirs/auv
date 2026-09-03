package dive

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// ── What a dive needs ────────────────────────────────────────────────────────

// Part is what one half of a dive needs of a machine: the simulator's share,
// or the controller's.
type Part struct {
	GPU            bool    `json:"gpu"`
	GPUMemoryBytes int64   `json:"gpuMemoryBytes"`
	CPU            float64 `json:"cpu"`
	MemoryBytes    int64   `json:"memoryBytes"`
}

// Needs is what a dive needs, assembled from its parts.
//
// The simulator always needs a card. A controller needs one only if it says
// so — a hand-written loop does not, a policy that is a model does — and how
// much of one is its stack's to declare when it is deployed.
type Needs struct {
	Simulator  Part  `json:"simulator"`
	Controller *Part `json:"controller,omitempty"`
}

const gib = int64(1) << 30

// What a simulator takes, measured on the box on 3 September 2026 with the
// Looe Key reef open: the interactive runtime held sixteen gigabytes of the
// card and eleven of the host, and batch a little less. Rounded up, because
// a placement that fits exactly fits until the next frame. A request may say
// otherwise for a runtime it knows better than this does.
var simulatorNeeds = map[Mode]Part{
	Interactive: {GPU: true, GPUMemoryBytes: 20 * gib, CPU: 4, MemoryBytes: 16 * gib},
	Batch:       {GPU: true, GPUMemoryBytes: 16 * gib, CPU: 4, MemoryBytes: 12 * gib},
}

// What a controller takes when its stack said nothing: what the agent has
// always bounded it to.
var controllerDefault = Part{CPU: 2, MemoryBytes: 4 * gib}

// A controller that wants a card and did not say how much of it.
const controllerGPUDefault = 8 * gib

// NeedsFor assembles what a run will need.
//
// `stack` is the stack's declaration, `wantsGPU` its older flag, and `asked`
// is what the request said, which wins over both: whoever asks for a dive
// may know the runtime better than the platform's measurements do.
func NeedsFor(mode Mode, stack json.RawMessage, wantsGPU bool, asked json.RawMessage,
	hasController bool) (Needs, error) {
	needs := Needs{Simulator: simulatorNeeds[mode]}
	if hasController {
		part := controllerDefault
		if len(stack) > 0 && string(stack) != "null" {
			var declared Part
			if err := json.Unmarshal(stack, &declared); err != nil {
				return Needs{}, fmt.Errorf("%w: the stack's needs could not be read: %v", domain.ErrInvalid, err)
			}
			part = fill(part, declared)
		}
		if wantsGPU {
			part.GPU = true
		}
		if part.GPU && part.GPUMemoryBytes == 0 {
			part.GPUMemoryBytes = controllerGPUDefault
		}
		if part.GPUMemoryBytes > 0 {
			part.GPU = true
		}
		needs.Controller = &part
	}
	if len(asked) > 0 && string(asked) != "null" {
		var override struct {
			Simulator  *Part `json:"simulator"`
			Controller *Part `json:"controller"`
		}
		if err := json.Unmarshal(asked, &override); err != nil {
			return Needs{}, fmt.Errorf("%w: the needs could not be read: %v", domain.ErrInvalid, err)
		}
		if override.Simulator != nil {
			needs.Simulator = fill(needs.Simulator, *override.Simulator)
			needs.Simulator.GPU = true
		}
		if override.Controller != nil && needs.Controller != nil {
			part := fill(*needs.Controller, *override.Controller)
			if part.GPUMemoryBytes > 0 {
				part.GPU = true
			}
			needs.Controller = &part
		}
	}
	if err := needs.Validate(); err != nil {
		return Needs{}, err
	}
	return needs, nil
}

// fill takes what `said` states and keeps `base` for what it left at zero.
func fill(base, said Part) Part {
	out := base
	if said.GPUMemoryBytes > 0 {
		out.GPUMemoryBytes = said.GPUMemoryBytes
	}
	if said.CPU > 0 {
		out.CPU = said.CPU
	}
	if said.MemoryBytes > 0 {
		out.MemoryBytes = said.MemoryBytes
	}
	if said.GPU {
		out.GPU = true
	}
	return out
}

// Validate reports whether the needs are ones a machine could have.
func (n Needs) Validate() error {
	parts := []Part{n.Simulator}
	if n.Controller != nil {
		parts = append(parts, *n.Controller)
	}
	for _, part := range parts {
		if part.GPUMemoryBytes < 0 || part.CPU < 0 || part.MemoryBytes < 0 {
			return fmt.Errorf("%w: a need is not negative", domain.ErrInvalid)
		}
		if part.GPU && part.GPUMemoryBytes == 0 {
			return fmt.Errorf("%w: a part that needs a card says how much of it", domain.ErrInvalid)
		}
	}
	if !n.Simulator.GPU || n.Simulator.GPUMemoryBytes == 0 {
		return fmt.Errorf("%w: a simulator needs a card", domain.ErrInvalid)
	}
	return nil
}

// CPU is the whole dive's processors.
func (n Needs) CPU() float64 {
	total := n.Simulator.CPU
	if n.Controller != nil {
		total += n.Controller.CPU
	}
	return total
}

// MemoryBytes is the whole dive's host memory.
func (n Needs) MemoryBytes() int64 {
	total := n.Simulator.MemoryBytes
	if n.Controller != nil {
		total += n.Controller.MemoryBytes
	}
	return total
}

// Cards is how many cards the dive holds at least: one, or two when the
// controller cannot share the simulator's.
func (n Needs) Cards() int {
	if n.Controller != nil && n.Controller.GPU {
		return 2
	}
	return 1
}

// LargestPartBytes is the most any one part needs of one card, which is what
// the smallest card that could ever take this dive has to have.
func (n Needs) LargestPartBytes() int64 {
	most := n.Simulator.GPUMemoryBytes
	if n.Controller != nil && n.Controller.GPUMemoryBytes > most {
		most = n.Controller.GPUMemoryBytes
	}
	return most
}

// OneCardBytes is what the whole dive needs of a single card, when it is to
// sit on one.
func (n Needs) OneCardBytes() int64 {
	total := n.Simulator.GPUMemoryBytes
	if n.Controller != nil {
		total += n.Controller.GPUMemoryBytes
	}
	return total
}

// ── Where it goes ────────────────────────────────────────────────────────────

// Card is one device as the placement sees it: what it has and what is
// already held on it.
type Card struct {
	ID          string
	TargetID    string
	Index       int
	UUID        string
	Model       string
	MemoryBytes int64
	HeldBytes   int64
	Enabled     bool
}

// Free is what is left on the card.
func (c Card) Free() int64 { return c.MemoryBytes - c.HeldBytes }

// Host is what the machine behind the cards has, and what is already held.
type Host struct {
	CPU             float64
	MemoryBytes     int64
	HeldCPU         float64
	HeldMemoryBytes int64
}

// Hold is one part of a run on one card.
type Hold struct {
	Part           string `json:"part"`
	DeviceID       string `json:"deviceId"`
	DeviceIndex    int    `json:"deviceIndex"`
	DeviceUUID     string `json:"deviceUuid"`
	Model          string `json:"model,omitempty"`
	GPUMemoryBytes int64  `json:"gpuMemoryBytes"`
}

// Place decides where a dive goes on these cards right now, or reports that
// it cannot go anywhere yet.
//
// The simulator takes the card with the most room, which spreads dives
// across a host's cards rather than stacking them on the first. A controller
// that wants a card prefers the simulator's, so that one dive occupies one
// card when it can and leaves the other whole for the next; when the
// simulator's card cannot take it, it takes the card with the most room
// among the rest. Processors and memory are the host's and are checked as a
// whole.
func Place(needs Needs, cards []Card, host Host) ([]Hold, bool) {
	if host.CPU > 0 && host.HeldCPU+needs.CPU() > host.CPU {
		return nil, false
	}
	if host.MemoryBytes > 0 && host.HeldMemoryBytes+needs.MemoryBytes() > host.MemoryBytes {
		return nil, false
	}
	usable := make([]Card, 0, len(cards))
	for _, card := range cards {
		if card.Enabled {
			usable = append(usable, card)
		}
	}
	sort.SliceStable(usable, func(i, j int) bool {
		if usable[i].Free() != usable[j].Free() {
			return usable[i].Free() > usable[j].Free()
		}
		return usable[i].Index < usable[j].Index
	})

	var simulator *Card
	for i := range usable {
		if usable[i].Free() >= needs.Simulator.GPUMemoryBytes {
			simulator = &usable[i]
			break
		}
	}
	if simulator == nil {
		return nil, false
	}
	holds := []Hold{{Part: "simulator", DeviceID: simulator.ID, DeviceIndex: simulator.Index,
		DeviceUUID: simulator.UUID, Model: simulator.Model,
		GPUMemoryBytes: needs.Simulator.GPUMemoryBytes}}

	if needs.Controller == nil || !needs.Controller.GPU {
		return holds, true
	}
	want := needs.Controller.GPUMemoryBytes
	if simulator.Free()-needs.Simulator.GPUMemoryBytes >= want {
		return append(holds, Hold{Part: "controller", DeviceID: simulator.ID,
			DeviceIndex: simulator.Index, DeviceUUID: simulator.UUID, Model: simulator.Model,
			GPUMemoryBytes: want}), true
	}
	for i := range usable {
		card := &usable[i]
		if card.ID == simulator.ID {
			continue
		}
		if card.Free() >= want {
			return append(holds, Hold{Part: "controller", DeviceID: card.ID,
				DeviceIndex: card.Index, DeviceUUID: card.UUID, Model: card.Model,
				GPUMemoryBytes: want}), true
		}
	}
	return nil, false
}

// CouldEverFit says whether these cards, empty, could take the dive at all —
// which is the difference between a request to queue and one to refuse.
func CouldEverFit(needs Needs, cards []Card, host Host) (bool, string) {
	empty := make([]Card, 0, len(cards))
	for _, card := range cards {
		card.HeldBytes = 0
		empty = append(empty, card)
	}
	if host.CPU > 0 && needs.CPU() > host.CPU {
		return false, fmt.Sprintf("this dive needs %.0f processors and the host has %.0f",
			needs.CPU(), host.CPU)
	}
	if host.MemoryBytes > 0 && needs.MemoryBytes() > host.MemoryBytes {
		return false, fmt.Sprintf("this dive needs %s of memory and the host has %s",
			Gigabytes(needs.MemoryBytes()), Gigabytes(host.MemoryBytes))
	}
	if _, ok := Place(needs, empty, Host{}); ok {
		return true, ""
	}
	var largest int64
	for _, card := range empty {
		if card.Enabled && card.MemoryBytes > largest {
			largest = card.MemoryBytes
		}
	}
	if largest == 0 {
		return false, "no card on this queue is enabled"
	}
	if needs.Cards() == 2 && len(empty) < 2 && needs.OneCardBytes() > largest {
		return false, fmt.Sprintf("the simulator and the controller together need %s of one card and the largest has %s, and there is no second card",
			Gigabytes(needs.OneCardBytes()), Gigabytes(largest))
	}
	return false, fmt.Sprintf("this dive needs %s of one card and the largest on this queue has %s",
		Gigabytes(needs.LargestPartBytes()), Gigabytes(largest))
}

// WaitingFor says what a queued dive is waiting on, in words.
func WaitingFor(needs Needs) string {
	if needs.Controller != nil && needs.Controller.GPU {
		return fmt.Sprintf("a card with %s free for the simulator and %s for the controller",
			Gigabytes(needs.Simulator.GPUMemoryBytes), Gigabytes(needs.Controller.GPUMemoryBytes))
	}
	return fmt.Sprintf("a card with %s free", Gigabytes(needs.Simulator.GPUMemoryBytes))
}

// Gigabytes renders bytes the way a person reads a card's memory.
func Gigabytes(bytes int64) string {
	value := float64(bytes) / float64(gib)
	if value == float64(int64(value)) {
		return fmt.Sprintf("%d GiB", int64(value))
	}
	return fmt.Sprintf("%.1f GiB", value)
}

// Placement is where a run stands with the scheduler, for whoever asked.
type Placement struct {
	// placed | queued | over
	State      string `json:"state"`
	Target     string `json:"target,omitempty"`
	Holds      []Hold `json:"holds"`
	Position   int    `json:"position,omitempty"`
	Ahead      int    `json:"ahead,omitempty"`
	WaitingFor string `json:"waitingFor,omitempty"`
}
