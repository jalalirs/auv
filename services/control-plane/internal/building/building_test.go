package building

import "testing"

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

func TestAFlatSeabedNeedsNoSource(t *testing.T) {
	depth, none := 8.0, false
	flat := Brief{Centre: [2]float64{22.3, 38.85}, AcrossM: 300, FlatDepthM: &depth, Coral: &none}
	if err := flat.Validate(); err != nil {
		t.Fatalf("a flat seabed 8 m down, no sources: %v", err)
	}
	for _, d := range []float64{0.1, 61} {
		deep := d
		if (Brief{Centre: [2]float64{22.3, 38.85}, AcrossM: 300, FlatDepthM: &deep}).Validate() == nil {
			t.Errorf("a flat seabed %g m down was accepted", d)
		}
	}
	if (Brief{Centre: [2]float64{22.3, 38.85}, AcrossM: 50, FlatDepthM: &depth}).Validate() == nil {
		t.Error("a flat place 50 m across was accepted")
	}
	if describe(flat) != "a flat seabed at 8 m" {
		t.Errorf("described as %q", describe(flat))
	}
}
