package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/jalalirs/auv/services/control-plane/internal/dive"
)

func main() {
	var cases map[string][]struct {
		Chosen   map[string]string `json:"chosen"`
		Score    float64           `json:"score"`
		HeldBack bool              `json:"heldBack"`
	}
	raw, _ := os.ReadFile(os.Args[1])
	if err := json.Unmarshal(raw, &cases); err != nil {
		panic(err)
	}
	out := map[string]dive.Findings{}
	for name, runs := range cases {
		flown := []dive.Flown{}
		for _, one := range runs {
			flown = append(flown, dive.Flown{
				Chosen: one.Chosen, State: "succeeded", Score: one.Score,
				Survived: one.Score >= 0.8, HeldBack: one.HeldBack,
			})
		}
		out[name] = dive.What(flown, 0.8)
	}
	said, _ := json.MarshalIndent(out, "", " ")
	fmt.Println(string(said))
}
