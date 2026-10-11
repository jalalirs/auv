package building

import (
	"testing"
	"time"
)

func TestABriefSaysWhereAndHowDeep(t *testing.T) {
	good := Brief{Centre: [2]float64{22.3, 38.9}, AcrossM: 1000, Sources: []string{"gebco", "allen-coral-atlas"}}
	if err := good.Validate(); err != nil {
		t.Fatalf("a square on the Red Sea from public data: %v", err)
	}
	cases := map[string]Brief{
		"off the map":           {Centre: [2]float64{95, 0}, AcrossM: 1000, Sources: []string{"gebco"}},
		"too small":             {Centre: [2]float64{22, 38}, AcrossM: 10, Sources: []string{"gebco"}},
		"an unknown source":     {Centre: [2]float64{22, 38}, AcrossM: 1000, Sources: []string{"google-earth"}},
		"nothing says how deep": {Centre: [2]float64{22, 38}, AcrossM: 1000, Sources: []string{"allen-coral-atlas"}},
		"a file of no kind":     {Centre: [2]float64{22, 38}, AcrossM: 1000, Files: []File{{ObjectID: "obj_1", Use: "video"}}},
	}
	for name, brief := range cases {
		if brief.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
	survey := Brief{Centre: [2]float64{24.5, -81.4}, AcrossM: 800, Files: []File{{ObjectID: "obj_1", Use: "raster"}}}
	if err := survey.Validate(); err != nil {
		t.Fatalf("a client's own depth survey alone is enough: %v", err)
	}
}

func TestAStepIsReadAsTheBuildSaidIt(t *testing.T) {
	step := stepOf(time.Unix(0, 0), map[string]any{"step": "fetch", "say": "the coral atlas", "n": 3.0, "of": 6.0, "source": "allen-coral-atlas"})
	if step.Step != "fetch" || step.N != 3 || step.Of != 6 || step.Detail["source"] != "allen-coral-atlas" {
		t.Fatalf("%+v", step)
	}
}

func TestTheResultKeepsWhereThePlaceIsWeak(t *testing.T) {
	result := resultOf([]byte(`{"name":"x","from":{"acrossMetres":1000,"depth":{"weak":{"errorM":{"median":1.2}}}},"deepestM":30,"layers":{}}`))
	if result["depth"] == nil || result["deepestM"] != 30.0 || result["layers"] != nil {
		t.Fatalf("%+v", result)
	}
}

func TestARecordWithNaNInItIsStillRead(t *testing.T) {
	result := resultOf([]byte(`{"from":{"depth":{"weak":{"errorM":{"median":2.1}}},"models":{"curve":{"rmsM":NaN,"x":[1, -Infinity]}}},"deepestM":30}`))
	if result == nil || result["deepestM"] != 30.0 {
		t.Fatalf("a record with NaN in it came back as %v", result)
	}
}
