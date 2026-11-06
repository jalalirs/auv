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
   {"id":"ship-1","kind":"ship","x":0,"y":0},
   {"id":"platform-1","kind":"object","asset":"recon_1","x":5,"y":5}]}],
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

func TestAWorldsReefIsHandedOverAsItsColonies(t *testing.T) {
	doc := `{"iocean":"world/1","name":"Tank","frame":{"extentM":[2,1]},"georef":null,
	 "layers":[{"id":"reef","kind":"reef","items":[
	   {"id":"coral-1","kind":"coral","form":"table","x":0.1,"y":0.2,"sizeM":0.3,"headingDeg":0,"built":true,"prim":"Tank/Coral0"},
	   {"id":"n1","kind":"note","x":0,"y":0}]},
	  {"id":"structures","kind":"structures","items":[{"id":"t1","kind":"transponder","x":1,"y":0}]}]}`
	got, err := WorldColonies("ver_1", json.RawMessage(doc))
	if err != nil {
		t.Fatal(err)
	}
	var reef struct {
		Version string            `json:"version"`
		Items   []json.RawMessage `json:"items"`
	}
	if err := json.Unmarshal(got, &reef); err != nil || reef.Version != "ver_1" || len(reef.Items) != 1 || !strings.Contains(string(reef.Items[0]), `"prim":"Tank/Coral0"`) {
		t.Fatalf("handed over %s", got)
	}
	// A big reef hands over only its edits, and the package they were made on.
	edits := `{"iocean":"world/1","name":"Al Fahal","frame":{"extentM":[3000,3000]},"georef":null,
	 "layers":[{"id":"reef","kind":"reef","params":{"colonies":1039632,"colonyEdits":true,"editedOn":"ver_pkg"},"items":[
	   {"id":"coral-17","kind":"coral","form":"table","x":3,"y":4,"sizeM":0.8,"headingDeg":30,"built":true}]}]}`
	got, err = WorldColonies("ver_2", json.RawMessage(edits))
	if err != nil || !strings.Contains(string(got), `"partial":true`) || !strings.Contains(string(got), `"package":"ver_pkg"`) {
		t.Fatalf("a big reef handed over %s (%v)", got, err)
	}
	// A world that lists no colonies keeps the build's, rather than saying all are gone.
	if got, _ := WorldColonies("ver_1", json.RawMessage(aWorld)); got != nil {
		t.Fatalf("a world with no coral items handed over %s", got)
	}
}
