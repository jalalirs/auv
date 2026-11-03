package catalog

import (
	"encoding/json"
	"strings"
	"testing"
)

const aWorld = `{"iocean":"world/1","name":"Al Fahal","frame":{"extentM":[3000,3000]},
 "georef":{"origin":{"lat":22.284,"lon":38.962}},
 "layers":[{"id":"water","kind":"water"},
  {"id":"structures","kind":"structures","items":[
   {"id":"frame-1","kind":"nursery-frame","x":10,"y":-4},
   {"id":"ship-1","kind":"ship","x":0,"y":0}]}],
 "bake":{"version":"ver_1"}}`

func TestAWorldIsReadAsTheThingsInItsStructures(t *testing.T) {
	if err := ValidateWorld(json.RawMessage(aWorld)); err != nil {
		t.Fatal(err)
	}
	layout, err := WorldThings("ver_2", json.RawMessage(aWorld))
	if err != nil {
		t.Fatal(err)
	}
	var read struct {
		Version string           `json:"version"`
		Things  []map[string]any `json:"things"`
	}
	if err := json.Unmarshal(layout, &read); err != nil {
		t.Fatal(err)
	}
	if read.Version != "ver_2" || len(read.Things) != 2 || read.Things[0]["id"] != "frame-1" {
		t.Fatalf("read %s", layout)
	}
	if WorldBake(json.RawMessage(aWorld)) != "ver_1" {
		t.Fatal("the bake was not read")
	}
}

func TestAWorldIsRefusedWhenItCannotBeFlown(t *testing.T) {
	for name, document := range map[string]string{
		"not a world":   `{"iocean":"layout"}`,
		"unknown layer": strings.Replace(aWorld, `"kind":"water"`, `"kind":"weather"`, 1),
		"repeated id":   strings.Replace(aWorld, `"ship-1"`, `"frame-1"`, 1),
		"no extent":     strings.Replace(aWorld, `[3000,3000]`, `[0,3000]`, 1),
	} {
		if ValidateWorld(json.RawMessage(document)) == nil {
			t.Errorf("%s was accepted", name)
		}
	}
}
