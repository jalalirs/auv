package exec

import "time"

// Step is one thing a job said it was doing, read from the progress lines it
// printed: {"progress": {"step": ..., "say": ..., "n": ..., "of": ...}}.
// Anything else on the line is kept as its detail.
type Step struct {
	At     time.Time      `json:"at"`
	Step   string         `json:"step"`
	Say    string         `json:"say"`
	N      int            `json:"n,omitempty"`
	Of     int            `json:"of,omitempty"`
	Detail map[string]any `json:"detail,omitempty"`
}

// Progress reads a job's events for the steps it reported, and the last of
// what it printed, which is what somebody needs when it failed. A job the
// worker could not run at all printed nothing, and what it has instead is the
// worker's reason.
func Progress(events []Event) (steps []Step, said string) {
	steps = []Step{}
	for _, e := range events {
		if e.Kind != EventProgress {
			continue
		}
		if progress, ok := e.Detail["progress"].(map[string]any); ok {
			steps = append(steps, StepOf(e.OccurredAt, progress))
		}
		if out, ok := e.Detail["output"].(string); ok {
			said = out
		}
		if failure, ok := e.Detail["failure"].(string); ok {
			said = failure
		}
	}
	return steps, said
}

// StepOf reads one progress line.
func StepOf(at time.Time, said map[string]any) Step {
	step := Step{At: at, Detail: map[string]any{}}
	for k, v := range said {
		switch k {
		case "step":
			step.Step, _ = v.(string)
		case "say":
			step.Say, _ = v.(string)
		case "n":
			if f, ok := v.(float64); ok {
				step.N = int(f)
			}
		case "of":
			if f, ok := v.(float64); ok {
				step.Of = int(f)
			}
		default:
			step.Detail[k] = v
		}
	}
	if len(step.Detail) == 0 {
		step.Detail = nil
	}
	return step
}
