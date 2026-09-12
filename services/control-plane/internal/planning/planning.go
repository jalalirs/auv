// Package planning turns what somebody said into a plan a vehicle can fly.
//
// Drafting happens here rather than in the console for one reason: the key
// that reaches a model must not. A renderer that holds it hands it to every
// page it loads, and this platform's console is an application somebody
// installs. So the words go up, the plan comes back, and the secret stays on
// the machine that was given it.
//
// What comes back is checked before anyone sees it. A plan from a model is a
// plan from a stranger: it may name a manoeuvre the vehicle cannot fly or hand
// over to a step that is not in it, and either would be discovered halfway
// through a dive as a vehicle stopping in the water for no reason a person
// could see. The check is cheap and it is the whole reason this is a platform
// capability rather than a prompt.
//
// The shape of a plan is borrowed rather than invented — a graph of manoeuvres
// with parameters and a transition to the next, which is what an IMC plan is
// and what the tooling in this field already speaks.
package planning

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"
)

// DescribedBy is what a plan document says it is, so that a file found on its
// own can be recognised and the shape can change later without silence.
const DescribedBy = "coral.city/plan/1"

// Kinds are the manoeuvres this platform's vehicles can fly. Anything else is
// refused: a plan is only worth having if the thing it describes can be done.
var Kinds = []string{"goto", "follow-path", "station-keeping"}

// Manoeuvre is one step of a plan.
type Manoeuvre struct {
	ID     string             `json:"id"`
	Kind   string             `json:"kind"`
	At     map[string]float64 `json:"at,omitempty"`
	Points []map[string]any   `json:"points,omitempty"`
	Next   string             `json:"next,omitempty"`

	AltitudeM *float64 `json:"altitudeM,omitempty"`
	ArriveM   *float64 `json:"arriveM,omitempty"`
	SpeedMs   *float64 `json:"speedMs,omitempty"`
	HoldS     *float64 `json:"holdS,omitempty"`
	RadiusM   *float64 `json:"radiusM,omitempty"`
}

// Document is a whole plan: a name, where it starts, and the manoeuvres.
type Document struct {
	DescribedBy string      `json:"describedBy"`
	Plan        string      `json:"plan"`
	By          string      `json:"by,omitempty"`
	Start       string      `json:"start,omitempty"`
	Manoeuvres  []Manoeuvre `json:"manoeuvres"`
}

// Read is what came back from a drafting: the plan, what was understood, and
// what was not. The reading travels with the plan on purpose — somebody who
// cannot see what the machine heard cannot tell a good plan from a lucky one.
type Read struct {
	Plan   *Document `json:"plan"`
	Said   []string  `json:"read"`
	Missed []string  `json:"missed"`
	Why    string    `json:"why,omitempty"`
}

// WhatIsWrong lists everything wrong with a plan, in sentences. Empty means it
// can be flown.
func WhatIsWrong(document *Document) []string {
	if document == nil || len(document.Manoeuvres) == 0 {
		return []string{"the plan has no manoeuvres"}
	}
	wrong := []string{}
	seen := map[string]bool{}
	for at, manoeuvre := range document.Manoeuvres {
		name := strings.TrimSpace(manoeuvre.ID)
		switch {
		case name == "":
			wrong = append(wrong, fmt.Sprintf("manoeuvre %d has no id", at+1))
		case seen[name]:
			wrong = append(wrong, fmt.Sprintf("two manoeuvres are called %s", name))
		}
		seen[name] = true

		known := false
		for _, kind := range Kinds {
			if manoeuvre.Kind == kind {
				known = true
			}
		}
		if !known {
			called := manoeuvre.Kind
			if called == "" {
				called = "nameless"
			}
			wrong = append(wrong, fmt.Sprintf("%s is a %s manoeuvre, which this vehicle cannot fly",
				orIndex(name, at), called))
		}
		if manoeuvre.Kind == "follow-path" && len(manoeuvre.Points) == 0 {
			wrong = append(wrong, fmt.Sprintf("%s is a path with no points", orIndex(name, at)))
		}
		if (manoeuvre.Kind == "goto" || manoeuvre.Kind == "station-keeping") && len(manoeuvre.At) == 0 {
			wrong = append(wrong, fmt.Sprintf("%s does not say where", orIndex(name, at)))
		}
	}
	for _, manoeuvre := range document.Manoeuvres {
		if manoeuvre.Next != "" && !seen[manoeuvre.Next] {
			wrong = append(wrong, fmt.Sprintf("%s hands over to %s, which is not in this plan",
				manoeuvre.ID, manoeuvre.Next))
		}
	}
	if document.Start != "" && !seen[document.Start] {
		wrong = append(wrong, fmt.Sprintf("the plan starts at %s, which is not in it", document.Start))
	}
	return wrong
}

func orIndex(name string, at int) string {
	if name != "" {
		return name
	}
	return fmt.Sprintf("manoeuvre %d", at+1)
}

// Where the vehicle is when it is asked, which a plan needs because a plan is
// written in the world's coordinates and an instruction is not.
type From struct {
	X          float64 `json:"x"`
	Y          float64 `json:"y"`
	DepthM     float64 `json:"depthM"`
	HeadingDeg float64 `json:"headingDeg"`
}

// Drafter asks a model for a plan. Nothing here is clever: a prompt that
// states the format exactly, and a refusal to believe the answer until it has
// been checked.
//
// Two shapes of endpoint, because the useful ones are not all the same. The
// messages shape takes the system prompt as its own field and answers with
// content blocks; the completions shape — what vLLM, litellm and most
// gateways speak — takes the system prompt as the first message and answers
// with choices. Which one is in front of us is read off the URL rather than
// configured, because an operator who has a URL should not also have to know
// what to call it.
type Drafter struct {
	URL   string
	Key   string
	Model string
	// How much the model may spend answering. Generous by default: a model
	// that reasons before it answers spends most of this thinking, and one cut
	// short returns its thinking with no plan attached — which looks exactly
	// like a model that cannot plan.
	MaxTokens int
	Client    *http.Client
}

// completions says whether this endpoint speaks the chat-completions shape.
func (d Drafter) completions() bool {
	return strings.Contains(d.URL, "/chat/completions") || strings.Contains(d.URL, "/completions")
}

func (d Drafter) maxTokens() int {
	if d.MaxTokens > 0 {
		return d.MaxTokens
	}
	return 12000
}

// Configured says whether this platform has been given a model to ask.
func (d Drafter) Configured() bool { return d.URL != "" && d.Key != "" }

const told = `You are planning one dive for an underwater vehicle. Answer with JSON only:
{"plan": "a short name", "start": "m1", "manoeuvres": [...]}.
A manoeuvre is {"id", "kind", "next"} where kind is one of goto, follow-path, station-keeping.
A "goto" has {"at": {"x", "y", "depthM" or "altitudeM"}, "arriveM"}.
A "follow-path" has {"points": [{"x","y"}], "altitudeM"} and is how a survey or a lawnmower is said.
A "station-keeping" has {"at": {...}, "radiusM"}.
The vehicle is at x=%.1f, y=%.1f, depth %.1f m, heading %.0f degrees, where x is north and y is east.
Metres throughout, and every position is in the world rather than relative to the vehicle.
Say nothing but the JSON.`

var firstObject = regexp.MustCompile(`(?s)\{.*\}`)

// Draft asks the model for a plan and checks what comes back.
func (d Drafter) Draft(ctx context.Context, said string, from From) (Read, error) {
	if !d.Configured() {
		return Read{
			Missed: []string{said},
			Why: "no model is configured for this platform, so it cannot be asked. " +
				"A plan can still be written by hand, or drafted at the command line " +
				"where a reader that needs no model understands the usual words.",
		}, nil
	}
	system := fmt.Sprintf(told, from.X, from.Y, from.DepthM, from.HeadingDeg)
	asking := map[string]any{"model": d.Model, "max_tokens": d.maxTokens()}
	if d.completions() {
		// Temperature nailed down: a plan is not a place for variety, and two
		// runs of one benchmark asking the same thing should get the same
		// answer or the benchmark is measuring the weather.
		asking["temperature"] = 0
		asking["messages"] = []map[string]string{
			{"role": "system", "content": system},
			{"role": "user", "content": said},
		}
	} else {
		asking["system"] = system
		asking["messages"] = []map[string]string{{"role": "user", "content": said}}
	}
	body, err := json.Marshal(asking)
	if err != nil {
		return Read{}, err
	}
	ask, err := http.NewRequestWithContext(ctx, http.MethodPost, d.URL, bytes.NewReader(body))
	if err != nil {
		return Read{}, err
	}
	ask.Header.Set("content-type", "application/json")
	if d.completions() {
		ask.Header.Set("authorization", "Bearer "+d.Key)
	} else {
		ask.Header.Set("x-api-key", d.Key)
		ask.Header.Set("anthropic-version", "2023-06-01")
	}

	client := d.Client
	if client == nil {
		client = &http.Client{Timeout: 90 * time.Second}
	}
	answered, err := client.Do(ask)
	if err != nil {
		return Read{Missed: []string{said}, Why: "the model could not be reached: " + err.Error()}, nil
	}
	defer answered.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(answered.Body, 1<<20))
	if err != nil {
		return Read{}, err
	}
	if answered.StatusCode >= 300 {
		return Read{Missed: []string{said},
			Why: fmt.Sprintf("the model refused: %s", strings.TrimSpace(shorten(string(raw))))}, nil
	}

	var envelope struct {
		// The messages shape.
		Content []struct {
			Text string `json:"text"`
		} `json:"content"`
		// And the completions shape.
		Choices []struct {
			Message struct {
				Content string `json:"content"`
				// Where a reasoning model puts its thinking. Read only to say
				// something useful when it thought instead of answering.
				Reasoning string `json:"reasoning"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return Read{Missed: []string{said}, Why: "the model did not answer with a plan"}, nil
	}
	answer := ""
	switch {
	case len(envelope.Content) > 0:
		answer = envelope.Content[0].Text
	case len(envelope.Choices) > 0:
		answer = envelope.Choices[0].Message.Content
		if strings.TrimSpace(answer) == "" && envelope.Choices[0].Message.Reasoning != "" {
			return Read{Missed: []string{said},
				Why: "the model spent its whole answer thinking and never got to the plan; " +
					"give it more room with CORAL_CITY_MODEL_MAX_TOKENS"}, nil
		}
	default:
		return Read{Missed: []string{said}, Why: "the model did not answer with a plan"}, nil
	}
	found := firstObject.FindString(answer)
	if found == "" {
		return Read{Missed: []string{said}, Why: "the model answered without a plan in it"}, nil
	}
	document := &Document{}
	if err := json.Unmarshal([]byte(found), document); err != nil {
		return Read{Missed: []string{said},
			Why: "the model's plan could not be read: " + shorten(err.Error())}, nil
	}
	if document.DescribedBy == "" {
		document.DescribedBy = DescribedBy
	}
	document.By = "a model: " + d.Model
	if wrong := WhatIsWrong(document); len(wrong) > 0 {
		return Read{Missed: []string{said},
			Why: "the model's plan cannot be flown: " + strings.Join(wrong, "; ")}, nil
	}
	name := document.Plan
	if name == "" {
		name = "a plan"
	}
	return Read{Plan: document, Said: []string{"a model read this as " + name}}, nil
}

func shorten(said string) string {
	if len(said) > 200 {
		return said[:200] + "…"
	}
	return said
}
