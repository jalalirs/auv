package dive

import (
	"encoding/json"
	"strings"
	"testing"
)

func box() []Card {
	return []Card{
		{ID: "d0", Index: 0, UUID: "GPU-0", Model: "RTX 5880", MemoryBytes: 47 * gib, Enabled: true},
		{ID: "d1", Index: 1, UUID: "GPU-1", Model: "RTX 5880", MemoryBytes: 47 * gib, Enabled: true},
	}
}

func hold(cards []Card, holds []Hold) []Card {
	for _, h := range holds {
		for i := range cards {
			if cards[i].ID == h.DeviceID {
				cards[i].HeldBytes += h.GPUMemoryBytes
			}
		}
	}
	return cards
}

func TestASimulatorAloneTakesTheEmptiestCard(t *testing.T) {
	needs, err := NeedsFor(Interactive, nil, false, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	cards := box()
	cards[0].HeldBytes = 10 * gib
	holds, ok := Place(needs, cards, Host{})
	if !ok || len(holds) != 1 || holds[0].DeviceIndex != 1 {
		t.Fatalf("expected the simulator on the emptier card 1, got %+v ok=%v", holds, ok)
	}
}

func TestAControllerSharesTheSimulatorsCardWhenItFits(t *testing.T) {
	needs, _ := NeedsFor(Batch, json.RawMessage(`{"gpuMemoryBytes":10737418240}`), false, nil, true)
	holds, ok := Place(needs, box(), Host{})
	if !ok || len(holds) != 2 {
		t.Fatalf("expected two holds, got %+v", holds)
	}
	if holds[0].DeviceIndex != holds[1].DeviceIndex {
		t.Fatalf("the controller should share the simulator's card: %+v", holds)
	}
}

func TestADiveMaySplitAcrossTwoCardsWhenOneCannotTakeItWhole(t *testing.T) {
	needs, _ := NeedsFor(Batch, json.RawMessage(`{"gpuMemoryBytes":10737418240}`), false, nil, true) // 16 + 10
	cards := box()
	cards[0].HeldBytes, cards[1].HeldBytes = 26*gib, 26*gib // two batch dives already on
	holds, ok := Place(needs, cards, Host{})
	if !ok || len(holds) != 2 || holds[0].DeviceIndex == holds[1].DeviceIndex {
		t.Fatalf("21 GiB free on each card takes the simulator on one and the controller on the other: %+v ok=%v", holds, ok)
	}
}

func TestAControllerThatCannotShareTakesTheOtherCard(t *testing.T) {
	needs, _ := NeedsFor(Interactive, json.RawMessage(`{"gpuMemoryBytes":32212254720}`), false, nil, true) // 30 GiB
	holds, ok := Place(needs, box(), Host{})
	if !ok || len(holds) != 2 || holds[0].DeviceIndex == holds[1].DeviceIndex {
		t.Fatalf("expected the controller on the other card, got %+v ok=%v", holds, ok)
	}
}

func TestTwoDivesTakeTwoCardsAndAThirdWaits(t *testing.T) {
	needs, _ := NeedsFor(Interactive, json.RawMessage(`{"gpuMemoryBytes":10737418240}`), false, nil, true) // 20 + 10
	cards := box()
	first, ok := Place(needs, cards, Host{})
	if !ok {
		t.Fatal("the first dive should be placed")
	}
	cards = hold(cards, first)
	second, ok := Place(needs, cards, Host{})
	if !ok || second[0].DeviceIndex == first[0].DeviceIndex {
		t.Fatalf("the second dive should take the other card: %+v", second)
	}
	cards = hold(cards, second)
	if _, ok := Place(needs, cards, Host{}); ok {
		t.Fatal("a third dive should wait: each card has 17 GiB free and the simulator alone needs 20")
	}
	if fits, _ := CouldEverFit(needs, cards, Host{}); !fits {
		t.Fatal("the third dive could fit once a card is free, so it queues rather than being refused")
	}
}

func TestADiveThatFitsNowhereIsRefusedWithTheReason(t *testing.T) {
	needs, _ := NeedsFor(Interactive, json.RawMessage(`{"gpuMemoryBytes":53687091200}`), false, nil, true) // 50 GiB
	fits, why := CouldEverFit(needs, box(), Host{})
	if fits {
		t.Fatal("a 50 GiB controller cannot fit a 47 GiB card")
	}
	if !strings.Contains(why, "50 GiB") || !strings.Contains(why, "47 GiB") {
		t.Fatalf("the reason should name both sizes: %q", why)
	}
}

func TestTheHostsProcessorsAndMemoryAreCounted(t *testing.T) {
	needs, _ := NeedsFor(Interactive, nil, false, nil, false)
	if _, ok := Place(needs, box(), Host{CPU: 8, MemoryBytes: 64 * gib, HeldCPU: 6}); ok {
		t.Fatal("two processors left is not enough for a simulator wanting four")
	}
	fits, why := CouldEverFit(needs, box(), Host{CPU: 2, MemoryBytes: 64 * gib})
	if fits || !strings.Contains(why, "processors") {
		t.Fatalf("a two-processor host can never run this: fits=%v why=%q", fits, why)
	}
}

func TestNeedsComeFromTheStackAndTheRequestInThatOrder(t *testing.T) {
	needs, err := NeedsFor(Interactive, json.RawMessage(`{"gpu":true}`), false,
		json.RawMessage(`{"simulator":{"gpuMemoryBytes":25769803776}}`), true)
	if err != nil {
		t.Fatal(err)
	}
	if needs.Simulator.GPUMemoryBytes != 24*gib {
		t.Fatalf("the request's simulator size should win: %v", needs.Simulator)
	}
	if needs.Controller == nil || !needs.Controller.GPU || needs.Controller.GPUMemoryBytes != controllerGPUDefault {
		t.Fatalf("a stack that wants a card without saying how much gets the default: %+v", needs.Controller)
	}
	if needs.Controller.CPU != 2 || needs.Controller.MemoryBytes != 4*gib {
		t.Fatalf("a controller keeps the agent's bounds unless it says otherwise: %+v", needs.Controller)
	}
	if WaitingFor(needs) != "a card with 24 GiB free for the simulator and 8 GiB for the controller" {
		t.Fatalf("waiting for reads wrong: %q", WaitingFor(needs))
	}
}
