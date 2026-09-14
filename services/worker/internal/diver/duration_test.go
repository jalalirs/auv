package diver

import "testing"

// A mission gets the time its stages ask for.
//
// It did not: a mission fell through to the five minutes a task with no stated
// limit gets, so a three-stage round asking for thirteen minutes was stopped
// part way through its first stage. That reads as a vehicle that failed, and
// the only thing that failed was arithmetic done before anybody knew what the
// dive was.
func TestHowLongAnObjectiveNeeds(t *testing.T) {
	for _, one := range []struct {
		what      string
		objective map[string]any
		want      float64
	}{
		{"a task that states its limit",
			map[string]any{"kind": "survey", "timeLimitS": 420.0}, 420.0},
		{"a task that states how long it holds",
			map[string]any{"kind": "hold-station", "seconds": 60.0}, 65.0},
		{"a task that states nothing",
			map[string]any{"kind": "reach"}, 300.0},
		{"a mission, which is the sum of its stages",
			map[string]any{"kind": "mission", "stages": []any{
				map[string]any{"kind": "survey", "timeLimitS": 360.0},
				map[string]any{"kind": "inspect", "timeLimitS": 180.0},
				map[string]any{"kind": "return", "timeLimitS": 240.0},
			}}, 780.0},
		{"a mission cut short on purpose",
			map[string]any{"kind": "mission", "timeLimitS": 300.0, "stages": []any{
				map[string]any{"kind": "survey", "timeLimitS": 360.0},
				map[string]any{"kind": "return", "timeLimitS": 240.0},
			}}, 300.0},
		{"a mission of missions",
			map[string]any{"kind": "mission", "stages": []any{
				map[string]any{"kind": "mission", "stages": []any{
					map[string]any{"kind": "survey", "timeLimitS": 100.0},
					map[string]any{"kind": "return", "timeLimitS": 50.0},
				}},
				map[string]any{"kind": "dock", "timeLimitS": 90.0},
			}}, 240.0},
	} {
		if got := longEnoughFor(one.objective); got != one.want {
			t.Errorf("%s: wanted %.0f s, got %.0f s", one.what, one.want, got)
		}
	}
}
