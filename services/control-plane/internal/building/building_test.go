package building

import (
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
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

func TestNoSourcesMeansEveryPublicSource(t *testing.T) {
	brief := withSources(Brief{Centre: [2]float64{22.3, 38.9}, AcrossM: 1000})
	if !brief.AllSources || len(brief.Sources) != len(Sources) || brief.Sources[0] != "allen-coral-atlas" {
		t.Fatalf("%+v", brief)
	}
	if err := (Brief{Centre: [2]float64{22.3, 38.9}, AcrossM: 1000}).Validate(); err != nil {
		t.Fatalf("an area and nothing else: %v", err)
	}
	if got := describe(brief); got != "every public source (allen-coral-atlas, gebco, icesat2, learned-depth, sentinel2)" {
		t.Errorf("described as %q", got)
	}
	named := withSources(Brief{Sources: []string{"gebco"}})
	if named.AllSources || len(named.Sources) != 1 {
		t.Errorf("named sources were replaced: %+v", named)
	}
	depth := 8.0
	if flat := withSources(Brief{FlatDepthM: &depth}); flat.AllSources || flat.Sources == nil || len(flat.Sources) != 0 {
		t.Errorf("a flat seabed was given sources: %+v", flat)
	}
	if based := withSources(Brief{Base: &Base{CityID: "city_1"}}); based.AllSources || len(based.Sources) != 0 {
		t.Errorf("a place built on a base was given sources: %+v", based)
	}
}

func TestAPlaceBuiltOnABaseTakesItsSquare(t *testing.T) {
	based := Brief{Base: &Base{CityID: "city_1"}}
	if err := based.Validate(); err != nil {
		t.Fatalf("a base and nothing else: %v", err)
	}
	depth := 8.0
	for name, brief := range map[string]Brief{
		"a base of no kind":  {Base: &Base{Kind: "survey", CityID: "city_1"}},
		"a base naming none": {Base: &Base{}},
		"flat and on a base": {Base: &Base{CityID: "city_1"}, FlatDepthM: &depth},
	} {
		if brief.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
	centre, across, field, err := squareOf(map[string]any{
		"from": map[string]any{"centre": map[string]any{"latitude": 22.284, "longitude": 38.962}, "acrossMetres": 3000.0},
		"mesh": map[string]any{"heightfield": map[string]any{"file": "./heights.f32"}}})
	if err != nil || centre != [2]float64{22.284, 38.962} || across != 3000 || field != "heights.f32" {
		t.Fatalf("%v %v %q %v", centre, across, field, err)
	}
	if _, _, _, err := squareOf(map[string]any{"from": map[string]any{}}); err == nil {
		t.Error("a site.json that says nowhere was read")
	}
}

func TestASurveyIsSomethingThatSaysHowDeep(t *testing.T) {
	brief := Brief{Centre: [2]float64{22.3, 38.85}, AcrossM: 500, Sources: []string{"allen-coral-atlas"},
		Survey: []string{"recon_b"}}
	if err := brief.Validate(); err != nil {
		t.Fatalf("a survey and the atlas: %v", err)
	}
	brief.Survey = []string{""}
	if brief.Validate() == nil {
		t.Error("a survey naming nothing was accepted")
	}
	brief.Survey = make([]string, MostSurveys+1)
	for i := range brief.Survey {
		brief.Survey[i] = "recon_b"
	}
	if brief.Validate() == nil {
		t.Error("too many surveys were accepted")
	}
}

func TestASurveyBecomesOneOfTheFiles(t *testing.T) {
	f := surveyFile(3, "recon_b", reconstructing.Survey{ObjectID: "obj_s", Name: "north.xyz", Use: "points",
		Datum: "LAT", ErrorM: 0.25, Citation: "KAUST multibeam 2025"})
	if f.Path != "files/03/north.xyz" || f.Use != "points" || f.Datum != "LAT" || f.ErrorM != 0.25 ||
		f.Citation != "KAUST multibeam 2025" || f.Asset != "recon_b" || f.ObjectID != "obj_s" {
		t.Fatalf("%+v", f)
	}
	if f := surveyFile(1, "recon_b", reconstructing.Survey{Name: "../.."}); f.Path != "files/01/survey" {
		t.Errorf("an unsafe name was staged at %s", f.Path)
	}
}
