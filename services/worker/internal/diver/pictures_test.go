package diver

import (
	"encoding/json"
	"testing"
)

// Whether a dive is drawn, and what it costs when the answer is wrong.
//
// Every dive with a task was rendered, because the recording was thought to
// need frames. Measured on the box — the same brief, the same card — the
// application runs the dive at 0.17x real time and the runner with no renderer
// runs it at 15x, and the two write the same poses file to the byte. So a bench
// of eight tasks was costing a day per controller to produce a video nobody
// watches, and a bench nobody runs twice is not a bench.
//
// Silence means pictures: somebody who set a dive up by hand wants to see it.
func TestWhetherAnybodyIsGoingToLookAtIt(t *testing.T) {
	no, yes := false, true
	for _, one := range []struct {
		what      string
		objective any
		want      bool
	}{
		{"a dive that says nothing is looked at", map[string]any{"kind": "reach"}, true},
		{"a dive with no objective at all", nil, true},
		{"a bench that asked for numbers", map[string]any{"kind": "reach", "pictures": &no}, false},
		{"a dive that asked for pictures", map[string]any{"kind": "reach", "pictures": &yes}, true},
	} {
		var raw json.RawMessage
		if one.objective != nil {
			encoded, err := json.Marshal(one.objective)
			if err != nil {
				t.Fatalf("%s: %v", one.what, err)
			}
			raw = encoded
		}
		claimed := Claimed{Objective: raw}
		if got := pictures(claimed); got != one.want {
			t.Errorf("%s: pictures = %v, want %v", one.what, got, one.want)
		}
	}
}

// An objective that is not the shape anybody expected is still flown, and it is
// flown drawn. A dive that refused to render because it could not read its own
// objective would be a dive with no video and no explanation.
func TestAnObjectiveNobodyCanReadIsStillDrawn(t *testing.T) {
	if !pictures(Claimed{Objective: json.RawMessage(`["not", "an", "object"]`)}) {
		t.Error("an unreadable objective should still be drawn")
	}
	if !pictures(Claimed{Objective: json.RawMessage(`{`)}) {
		t.Error("a broken objective should still be drawn")
	}
}

// A dive nobody looks at still leaves a record. The poses, the sensors, the
// task and the manifest are the dive's result; the video is the only thing a
// dry dive is short of, and the manifest says it is short of it.
func TestADiveNobodyLooksAtStillRecords(t *testing.T) {
	no := false
	encoded, err := json.Marshal(map[string]any{"kind": "survey", "pictures": &no})
	if err != nil {
		t.Fatal(err)
	}
	claimed := Claimed{Objective: encoded}
	if !recording(claimed) {
		t.Error("a dive flown for its numbers still records them")
	}
	if pictures(claimed) {
		t.Error("and it is not drawn")
	}
}
