package dive

import (
	"encoding/json"
	"testing"
)

// What a caller says about a mission's dive — who flies it, whether it is
// drawn — is laid over the mission's stages, not put in their place.
func TestWhatIsSaidIsLaidOverTheMissionNotInsteadOfIt(t *testing.T) {
	composed, err := layOver(json.RawMessage(`{"kind":"mission","stages":[{"kind":"survey"}]}`),
		json.RawMessage(`{"controller":"wary","pictures":false}`))
	if err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	if err := json.Unmarshal(composed, &got); err != nil {
		t.Fatal(err)
	}
	if got["kind"] != "mission" || got["controller"] != "wary" || got["pictures"] != false {
		t.Fatalf("composed %s", composed)
	}
	if stages, ok := got["stages"].([]any); !ok || len(stages) != 1 {
		t.Fatalf("the stages went missing: %s", composed)
	}
}
