package mapping

import (
	"math"
	"strings"
	"testing"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/exec"

	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
)

func number(v float64) *float64 { return &v }

func TestARequestIsOntoAPlaceOrOfItsOwn(t *testing.T) {
	good := []Request{
		{Mode: Onto, CityID: "city_1"},
		{Mode: Onto, CityID: "city_1", Start: &reconstructing.Point{Lat: 22.3, Lon: 38.9}, WithinM: 800, DepthM: number(12), Count: 3},
		{Mode: Own, Name: "Al Fahal transect"},
		{Mode: Own, Name: "x", AcrossM: 500, DepthM: number(5), Pad: "coral", HeadingDeg: number(90)},
	}
	for _, q := range good {
		if err := q.Validate(); err != nil {
			t.Errorf("%+v: %v", q, err)
		}
	}
	bad := map[string]Request{
		"no mode":              {CityID: "city_1"},
		"onto nowhere":         {Mode: Onto},
		"a search too narrow":  {Mode: Onto, CityID: "city_1", WithinM: 1},
		"too many candidates":  {Mode: Onto, CityID: "city_1", Count: 50},
		"a reef above the sea": {Mode: Onto, CityID: "city_1", DepthM: number(-3)},
		"a start off Earth":    {Mode: Onto, CityID: "city_1", Start: &reconstructing.Point{Lat: 100}},
		"a place with no name": {Mode: Own},
		"a place too small":    {Mode: Own, Name: "x", AcrossM: 50},
		"a seabed too deep":    {Mode: Own, Name: "x", DepthM: number(80)},
		"a pad of rock":        {Mode: Own, Name: "x", Pad: "rock"},
		"a heading past 360":   {Mode: Own, Name: "x", HeadingDeg: number(400)},
		"a heading of NaN":     {Mode: Own, Name: "x", HeadingDeg: number(math.NaN())},
	}
	for name, q := range bad {
		if q.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
}

func TestWhatIsLeftToADefaultIsWrittenDown(t *testing.T) {
	stated := reconstructing.Reconstruction{Brief: reconstructing.Brief{Start: &reconstructing.Point{Lat: 22.1, Lon: 38.7}}}
	own := withDefaults(Request{Mode: Own, Name: "x"}, stated)
	if own.Start.Lat != 22.1 || own.StartAssumed || own.AcrossM != 300 || *own.DepthM != 8 || own.Pad != "sand" || *own.HeadingDeg != 0 {
		t.Fatalf("%+v", own)
	}
	nowhere := withDefaults(Request{Mode: Own, Name: "x"}, reconstructing.Reconstruction{})
	if *nowhere.Start != NominalStart || !nowhere.StartAssumed {
		t.Fatalf("a reef nobody placed on Earth: %+v", nowhere)
	}
	onto := withDefaults(Request{Mode: Onto, CityID: "city_1"}, reconstructing.Reconstruction{})
	if onto.Start != nil || onto.StartAssumed || onto.WithinM != 400 || onto.Count != 5 {
		t.Fatalf("a search with no start looks everywhere and assumes nothing: %+v", onto)
	}
}

func TestAChoiceBecomesWhereTheReefIsLaid(t *testing.T) {
	found := []map[string]any{
		{"at": []any{12.0, -4.0}, "headingDeg": 30.0, "dz": -8.2, "fit": map[string]any{"rmsM": 0.3}, "matrix": []any{}},
	}
	first := 0
	placement, err := placementOf(Choice{Candidate: &first}, found)
	if err != nil || placement["headingDeg"] != 30.0 || placement["fit"] == nil || placement["matrix"] != nil {
		t.Fatalf("%v %v", placement, err)
	}
	second := 1
	if _, err := placementOf(Choice{Candidate: &second}, found); err == nil {
		t.Error("a candidate the search did not find was accepted")
	}
	by := Placement{At: [2]float64{3, 4}, HeadingDeg: 45, Dz: -1}
	placement, err = placementOf(Choice{Placement: &by}, found)
	if err != nil || placement["dz"] != -1.0 {
		t.Fatalf("by hand: %v %v", placement, err)
	}
	for _, wrong := range []Placement{{At: [2]float64{math.Inf(1), 0}}, {HeadingDeg: 361}, {Dz: math.NaN()}} {
		if _, err := placementOf(Choice{Placement: &wrong}, found); err == nil {
			t.Errorf("%+v was accepted", wrong)
		}
	}
	if _, err := placementOf(Choice{}, found); err == nil {
		t.Error("an empty choice was accepted")
	}
	if _, err := placementOf(Choice{Candidate: &first, Placement: &by}, found); err == nil {
		t.Error("a candidate and a placement at once were accepted")
	}
}

func TestTheSearchIsNotGivenThePieces(t *testing.T) {
	for path, want := range map[string]bool{"reconstruction.json": true, "surface.f32": true, "parts/part-1.pt": false, "parts/part-1.usdz": false} {
		if got := wanted(path, false); got != want {
			t.Errorf("the search staged %s: %v", path, got)
		}
		if !wanted(path, true) {
			t.Errorf("laying did not stage %s", path)
		}
	}
}

func TestAReefIsCalledBySlugInsideAPlace(t *testing.T) {
	cases := map[string]string{"GX010123": "gx010123", "Al Fahal (north) ": "al-fahal-north", "2026 dive": "reef-2026-dive", "": "reef"}
	for name, want := range cases {
		if got := handleOf(name); got != want {
			t.Errorf("handleOf(%q) = %q, want %q", name, got, want)
		}
	}
}

func TestAPlaceOfItsOwnIsASquareAroundTheStart(t *testing.T) {
	e := extentOf(reconstructing.Point{Lat: 22.3, Lon: 38.85}, 300)
	if math.Abs((e.North-e.South)*111320-300) > 0.5 || e.West >= 38.85 || e.East <= 38.85 {
		t.Fatalf("%+v", e)
	}
}

func TestAPlaceTakesOneToTwentyReefs(t *testing.T) {
	one := AssetRequest{ReconstructionID: "recon_1"}
	if err := (PlaceRequest{Assets: []AssetRequest{one, {ReconstructionID: "recon_2", WithinM: 800}}}).Validate(); err != nil {
		t.Fatalf("two reefs: %v", err)
	}
	many := make([]AssetRequest, MostAssets+1)
	for i := range many {
		many[i] = one
	}
	for name, q := range map[string]PlaceRequest{
		"no reefs":             {},
		"too many reefs":       {Assets: many},
		"a reef naming none":   {Assets: []AssetRequest{{}}},
		"a reef searching far": {Assets: []AssetRequest{{ReconstructionID: "recon_1", WithinM: 9000}}},
	} {
		if q.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
	if got := assetDefaults(one, reconstructing.Reconstruction{Brief: reconstructing.Brief{
		Start: &reconstructing.Point{Lat: 22.1, Lon: 38.7}}}); got.Start.Lat != 22.1 || got.WithinM != 400 || got.Count != 5 {
		t.Fatalf("%+v", got)
	}
}

func TestReefsAreCalledUniquelyInAPlace(t *testing.T) {
	got := namesOf([]string{"GX010", "GX010", "Al Fahal", "gx010"})
	want := []string{"gx010", "gx010-2", "al-fahal", "gx010-3"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("namesOf = %v, want %v", got, want)
		}
	}
}

func TestOneLayJobIsToldEveryReefStillInAndSizedByThem(t *testing.T) {
	assets := []Asset{
		{Ordinal: 0, ReconstructionID: "recon_1", Name: "gx010", Chosen: map[string]any{"at": []any{1.0, 2.0}, "headingDeg": 30.0, "dz": -8.0}},
		{Ordinal: 1, ReconstructionID: "recon_2", Name: "north", Chosen: map[string]any{"at": []any{5.0, 2.0}}, DroppedAt: &time.Time{}},
		{Ordinal: 2, ReconstructionID: "recon_1", Name: "gx010-2", Chosen: map[string]any{"at": []any{9.0, 2.0}}},
	}
	videos := map[string]reconstructing.Reconstruction{"recon_1": {ID: "recon_1",
		Brief: reconstructing.Brief{Video: reconstructing.Video{Name: "GX010.MP4", ObjectID: "obj_v"}}}}
	brief := layBrief(assets, videos)
	laid := brief["assets"].([]any)
	if len(laid) != 2 || brief["sink"] != 1.0 {
		t.Fatalf("%v", brief)
	}
	first := laid[0].(map[string]any)
	if first["name"] != "gx010" || first["path"] != "reconstruction/recon_1" ||
		first["video"].(map[string]any)["objectId"] != "obj_v" {
		t.Fatalf("%v", first)
	}

	settings := Settings{LayWalltimeSeconds: 16 * 3600, PackageBytes: 40 << 30, PackageCapBytes: 64 << 30}
	walltime, limit := laySize(2, 2<<30, settings)
	if walltime != 3600+2*2700 || limit != 64<<30 {
		t.Errorf("two reefs: %d s, %d bytes", walltime, limit)
	}
	if walltime, limit := laySize(1, 1<<30, settings); walltime != 6300 || limit != 41<<30 {
		t.Errorf("one reef: %d s, %d bytes", walltime, limit)
	}
	if walltime, _ := laySize(20, 0, settings); walltime != 16*3600 {
		t.Errorf("twenty reefs were given %d s", walltime)
	}

	label, notes := labelOf(Mapping{ID: "map_1", Assets: assets}, map[string]string{"recon_1": "GX010", "recon_2": "North"})
	if label != "GX010 and 1 more laid in" || !strings.Contains(notes, "recon_1, recon_1") || !strings.Contains(notes, "map_1") {
		t.Errorf("%q / %q", label, notes)
	}
}

func TestTheLayJobsLastWordSaysWhereEachWentAndWhatOverlaps(t *testing.T) {
	laid, overlaps := doneOf([]exec.Step{
		{Step: "lay", Say: "laying gx010"},
		{Step: "done", Say: "2 assets laid", Detail: map[string]any{
			"assets":   []any{map[string]any{"name": "gx010"}, map[string]any{"name": "north"}},
			"overlaps": []any{"gx010 and north come within 0.4 m"}}},
	})
	if len(laid) != 2 || len(overlaps) != 1 {
		t.Fatalf("%v %v", laid, overlaps)
	}
	if laid, overlaps := doneOf([]exec.Step{{Step: "lay"}}); laid != nil || overlaps != nil {
		t.Fatal("a lay job that has not finished said where things went")
	}
}
