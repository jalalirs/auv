package planning

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// A plan from a model is a plan from a stranger. What is protected here is the
// gate: whatever comes back is checked against what the vehicle can actually
// fly before anybody is shown it, because the alternative is discovering it
// halfway through a dive as a vehicle stopping in the water.

func TestWhatIsWrongNamesEveryFaultInSentences(t *testing.T) {
	wrong := WhatIsWrong(&Document{Manoeuvres: []Manoeuvre{
		{ID: "m1", Kind: "goto", At: map[string]float64{"x": 1, "y": 2}, Next: "m4"},
		{ID: "m1", Kind: "spiral-descent", At: map[string]float64{"x": 1, "y": 2}},
		{ID: "m2", Kind: "follow-path"},
		{ID: "m3", Kind: "goto"},
	}})
	for _, want := range []string{
		"two manoeuvres are called m1",
		"spiral-descent manoeuvre, which this vehicle cannot fly",
		"m2 is a path with no points",
		"m3 does not say where",
		"m1 hands over to m4, which is not in this plan",
	} {
		if !strings.Contains(strings.Join(wrong, " | "), want) {
			t.Errorf("nothing said %q; it said %v", want, wrong)
		}
	}
}

func TestAPlanThatCanBeFlownHasNothingWrongWithIt(t *testing.T) {
	if wrong := WhatIsWrong(&Document{Start: "m1", Manoeuvres: []Manoeuvre{
		{ID: "m1", Kind: "goto", At: map[string]float64{"x": 40, "y": 0, "depthM": 6}, Next: "m2"},
		{ID: "m2", Kind: "station-keeping", At: map[string]float64{"x": 40, "y": 0}},
	}}); len(wrong) != 0 {
		t.Fatalf("a good plan was refused: %v", wrong)
	}
}

func TestWithNoModelItSaysSoRatherThanFailing(t *testing.T) {
	read, err := Drafter{}.Draft(context.Background(), "survey the reef", From{})
	if err != nil {
		t.Fatalf("asking with no model configured should not be an error: %v", err)
	}
	if read.Plan != nil || !strings.Contains(read.Why, "no model is configured") {
		t.Fatalf("it did not say why it could not draft: %+v", read)
	}
}

func TestAModelsPlanIsCheckedBeforeItIsBelieved(t *testing.T) {
	answered := func(text string) *httptest.Server {
		return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"content": []map[string]string{{"text": text}},
			})
		}))
	}

	bad := answered(`{"plan": "off it goes", "start": "m1", "manoeuvres": ` +
		`[{"id": "m1", "kind": "teleport", "at": {"x": 1, "y": 2}}]}`)
	defer bad.Close()
	read, err := Drafter{URL: bad.URL, Key: "x", Model: "test"}.Draft(
		context.Background(), "teleport to the reef", From{})
	if err != nil {
		t.Fatal(err)
	}
	if read.Plan != nil {
		t.Fatal("a plan naming a manoeuvre the vehicle cannot fly was accepted")
	}
	if !strings.Contains(read.Why, "cannot fly") {
		t.Fatalf("and it did not say why: %q", read.Why)
	}

	good := answered("here you are:\n```json\n" +
		`{"plan": "north and hold", "start": "m1", "manoeuvres": ` +
		`[{"id": "m1", "kind": "goto", "at": {"x": 200, "y": 0, "depthM": 5}}]}` + "\n```")
	defer good.Close()
	read, err = Drafter{URL: good.URL, Key: "x", Model: "test"}.Draft(
		context.Background(), "go two hundred metres north", From{})
	if err != nil {
		t.Fatal(err)
	}
	if read.Plan == nil {
		t.Fatalf("a good plan was refused: %+v", read)
	}
	if read.Plan.DescribedBy != DescribedBy || read.Plan.By != "a model: test" {
		t.Fatalf("the plan does not say what it is or who wrote it: %+v", read.Plan)
	}
}

func TestAModelThatWillNotAnswerIsReportedRatherThanRaised(t *testing.T) {
	refused := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error": "slow down"}`))
	}))
	defer refused.Close()
	read, err := Drafter{URL: refused.URL, Key: "x", Model: "test"}.Draft(
		context.Background(), "survey the reef", From{})
	if err != nil {
		t.Fatalf("a model refusing is not this platform failing: %v", err)
	}
	if read.Plan != nil || !strings.Contains(read.Why, "refused") {
		t.Fatalf("it did not report the refusal: %+v", read)
	}
}

// The endpoints worth using are not all the same shape. A gateway in front of
// vLLM — which is what most local and hosted fleets are — speaks chat
// completions: the system prompt is the first message, the key is a bearer
// token, and the answer is in choices. Reading which one it is off the URL
// means an operator who has a URL does not also have to know what to call it.

func TestACompletionsEndpointIsSpokenToInItsOwnShape(t *testing.T) {
	var asked map[string]any
	var bearer string
	endpoint := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		bearer = r.Header.Get("authorization")
		_ = json.NewDecoder(r.Body).Decode(&asked)
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []map[string]any{
			{"message": map[string]string{"content": `{"plan": "north", "start": "m1", ` +
				`"manoeuvres": [{"id": "m1", "kind": "goto", "at": {"x": 200, "y": 0}}]}`}},
		}})
	}))
	defer endpoint.Close()

	read, err := Drafter{URL: endpoint.URL + "/v1/chat/completions", Key: "k", Model: "minimax"}.
		Draft(context.Background(), "go two hundred metres north", From{})
	if err != nil {
		t.Fatal(err)
	}
	if read.Plan == nil {
		t.Fatalf("a good plan was refused: %+v", read)
	}
	if bearer != "Bearer k" {
		t.Errorf("the key was not sent as a bearer token: %q", bearer)
	}
	messages, _ := asked["messages"].([]any)
	if len(messages) != 2 {
		t.Fatalf("the system prompt was not sent as a message: %v", asked["messages"])
	}
	first, _ := messages[0].(map[string]any)
	if first["role"] != "system" {
		t.Errorf("the first message is not the system prompt: %v", first["role"])
	}
	if asked["temperature"] != float64(0) {
		t.Errorf("a plan was asked for with temperature %v; it must be pinned", asked["temperature"])
	}
}

func TestAModelThatThinksItsWholeBudgetAwaySaysWhatToDo(t *testing.T) {
	// What MiniMax does when it is given two thousand tokens: it reasons for
	// all of them and the answer comes back empty. Reported as itself rather
	// than as "did not answer with a plan", because the remedy is a number.
	endpoint := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"choices": []map[string]any{
			{"message": map[string]string{"content": "", "reasoning": "The user wants a survey…"},
				"finish_reason": "length"},
		}})
	}))
	defer endpoint.Close()

	read, err := Drafter{URL: endpoint.URL + "/v1/chat/completions", Key: "k", Model: "minimax",
		MaxTokens: 2000}.Draft(context.Background(), "survey the reef", From{})
	if err != nil {
		t.Fatal(err)
	}
	if read.Plan != nil {
		t.Fatal("an empty answer was taken for a plan")
	}
	if !strings.Contains(read.Why, "MAX_TOKENS") {
		t.Fatalf("it did not say how to fix it: %q", read.Why)
	}
}
