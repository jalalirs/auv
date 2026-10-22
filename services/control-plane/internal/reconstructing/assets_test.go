package reconstructing

import (
	"math"
	"strings"
	"testing"
)

func metres(m float64) *float64 { return &m }

func TestAnAssetBriefSaysWhatItIsAndNothingImpossible(t *testing.T) {
	survey := AssetBrief{Kind: KindBathymetry, Object: "obj_1", File: &SourceFile{Name: "north.tif"},
		Datum: "MSL", ErrorM: 0.3}
	model := AssetBrief{Kind: KindStructure, Type: "platform", Object: "obj_2", Model: &Model{Name: "jacket.GLB"}}
	route := AssetBrief{Kind: KindStructure, Type: "pipeline",
		Route: &Route{Points: [][2]float64{{22.30, 38.85}, {22.31, 38.86}}, DiameterM: 0.5, Burial: metres(0.3)}}
	for name, brief := range map[string]AssetBrief{"a survey": survey, "a model": model, "a route": route} {
		if err := brief.withDefaults().Validate(); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
	if got := survey.withDefaults(); got.File.Format != "geotiff" {
		t.Errorf("a .tif was read as %q", got.File.Format)
	}
	if got := model.withDefaults(); got.Model.Format != "glb" || got.Model.Scale != 1 || got.Model.Up != "y" || got.Meets != Stands {
		t.Errorf("a model's defaults: %+v %+v", got, got.Model)
	}
	if got := route.withDefaults(); got.Meets != Drapes || got.madeFrom() != FromRoute {
		t.Errorf("a route's defaults: %+v", got)
	}
	if survey.madeFrom() != FromSurvey || model.madeFrom() != FromModel {
		t.Error("what an asset is made from was misread")
	}

	with := func(b AssetBrief, change func(*AssetBrief)) AssetBrief {
		b = b.withDefaults()
		if b.File != nil {
			file := *b.File
			b.File = &file
		}
		if b.Model != nil {
			m := *b.Model
			b.Model = &m
		}
		if b.Route != nil {
			r := *b.Route
			b.Route = &r
		}
		change(&b)
		return b
	}
	cases := map[string]AssetBrief{
		"a reef":                       {Kind: KindReef},
		"no kind":                      {},
		"a kind of nothing":            {Kind: "wreck"},
		"a survey with no object":      with(survey, func(b *AssetBrief) { b.Object = "" }),
		"a survey of no format":        with(survey, func(b *AssetBrief) { b.File.Format = "las" }),
		"a survey named nothing known": (AssetBrief{Kind: KindBathymetry, Object: "obj_1", Datum: "MSL", ErrorM: 1}).withDefaults(),
		"a survey with no datum":       with(survey, func(b *AssetBrief) { b.Datum = " " }),
		"a survey with no error":       with(survey, func(b *AssetBrief) { b.ErrorM = 0 }),
		"a survey wrong by NaN":        with(survey, func(b *AssetBrief) { b.ErrorM = math.NaN() }),
		"a survey with a type":         with(survey, func(b *AssetBrief) { b.Type = "platform" }),
		"a structure of no type":       with(model, func(b *AssetBrief) { b.Type = "ship" }),
		"a structure that floats":      with(model, func(b *AssetBrief) { b.Meets = "floats" }),
		"a model that drapes":          with(model, func(b *AssetBrief) { b.Meets = Drapes }),
		"a model with no object":       with(model, func(b *AssetBrief) { b.Object = "" }),
		"a model of no format":         with(model, func(b *AssetBrief) { b.Model.Format = "fbx" }),
		"a model scaled to nothing":    with(model, func(b *AssetBrief) { b.Model.Scale = -1 }),
		"a model up sideways":          with(model, func(b *AssetBrief) { b.Model.Up = "x" }),
		"a model and a route":          with(model, func(b *AssetBrief) { b.Route = route.Route }),
		"a structure of neither":       {Kind: KindStructure, Type: "other", Meets: Stands},
		"a route of one point":         with(route, func(b *AssetBrief) { b.Route.Points = b.Route.Points[:1] }),
		"a route off the Earth":        with(route, func(b *AssetBrief) { b.Route.Points = [][2]float64{{0, 0}, {91, 0}} }),
		"a route with no width":        with(route, func(b *AssetBrief) { b.Route.DiameterM = 0 }),
		"a route buried in the air":    with(route, func(b *AssetBrief) { b.Route.Burial = metres(-1) }),
		"a route of a platform":        with(route, func(b *AssetBrief) { b.Type = "platform" }),
		"a route that stands":          with(route, func(b *AssetBrief) { b.Meets = Stands }),
		"a route with a file":          with(route, func(b *AssetBrief) { b.Object = "obj_3" }),
	}
	for name, brief := range cases {
		if brief.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
}

func TestTheImportJobFindsTheFileUnderItsOwnSafeName(t *testing.T) {
	cases := map[[2]string]string{
		{"north.tif", "geotiff"}:    "source/north.tif",
		{"../../etc/passwd", "xyz"}: "source/passwd",
		{"", "glb"}:                 "source/model.glb",
		{"..", "geotiff"}:           "source/survey.tif",
		{"jacket (v2).obj", "obj"}:  "source/jacket_v2_.obj",
	}
	for in, want := range cases {
		if got := sourcePath(in[0], in[1]); got != want {
			t.Errorf("sourcePath(%q, %q) = %q, want %q", in[0], in[1], got, want)
		}
	}
	if got := assetName(AssetBrief{Kind: KindStructure, Type: "pipeline", Route: &Route{}}); got != "a pipeline" {
		t.Errorf("an unnamed route is called %q", got)
	}
	if got := assetName(AssetBrief{Kind: KindBathymetry, File: &SourceFile{Name: "north.tif"}}); got != "north" {
		t.Errorf("a survey is called %q", got)
	}
}

func TestAnImportsManifestIsTheAssetThatWasAskedFor(t *testing.T) {
	survey := Reconstruction{Kind: KindBathymetry, MadeFrom: FromSurvey}
	record := map[string]any{"kind": "bathymetry", "footprint": map[string]any{"bbox": []any{22.0, 38.0, 22.1, 38.1}},
		"file": "north.tif", "preview": "preview.png"}
	held := map[string]bool{"asset.json": true, "north.tif": true, "preview.png": true}
	if err := checkAsset(survey, record, held); err != nil {
		t.Fatalf("a whole survey: %v", err)
	}
	if err := checkAsset(survey, record, map[string]bool{"preview.png": true}); err == nil {
		t.Error("a survey without its file was accepted")
	}
	record["file"] = map[string]any{"name": "north.tif", "format": "geotiff"}
	if err := checkAsset(survey, record, held); err != nil {
		t.Errorf("a survey's file named as {name, format}: %v", err)
	}
	route := map[string]any{"kind": "structure", "footprint": map[string]any{"bbox": []any{1.0}}}
	if err := checkAsset(Reconstruction{Kind: KindStructure, MadeFrom: FromRoute}, route, map[string]bool{}); err != nil {
		t.Errorf("a route needs no model: %v", err)
	}
	if err := checkAsset(Reconstruction{Kind: KindStructure, MadeFrom: FromModel}, record, held); err == nil ||
		!strings.Contains(err.Error(), "bathymetry") {
		t.Errorf("a survey taken for a structure: %v", err)
	}
	model := map[string]any{"kind": "structure", "footprint": map[string]any{"sizeM": []any{20.0, 20.0, 40.0}}}
	structure := Reconstruction{Kind: KindStructure, MadeFrom: FromModel}
	if err := checkAsset(structure, model, map[string]bool{"model.usdc": true}); err != nil {
		t.Fatalf("a whole model: %v", err)
	}
	if err := checkAsset(structure, model, map[string]bool{}); err == nil {
		t.Error("a structure without its model was accepted")
	}
	if err := checkAsset(structure, map[string]any{"kind": "structure"}, map[string]bool{"model.usdc": true}); err == nil {
		t.Error("an asset with no footprint was accepted")
	}
}

func TestTheLibraryShowsEveryKindTheSameWay(t *testing.T) {
	structure := asAsset(View{State: "ready", Reconstruction: Reconstruction{ID: "recon_2", Kind: KindStructure,
		MadeFrom: FromRoute, Structure: &Structure{Type: "pipeline", Meets: Drapes}, Asset: &AssetBrief{Kind: KindStructure},
		Manifest: map[string]any{"footprint": map[string]any{"bbox": []any{1.0}}, "stats": map[string]any{"lengthM": 140.0}}}})
	if structure.Type != "pipeline" || structure.Meets != Drapes || structure.Stats["lengthM"] != 140.0 ||
		structure.Footprint["bbox"] == nil || structure.MadeFrom != FromRoute {
		t.Fatalf("%+v", structure)
	}
	reef := asAsset(View{State: "ready", Reconstruction: Reconstruction{ID: "recon_1", Kind: KindReef, MadeFrom: FromVideo,
		Manifest: map[string]any{"extentM": []any{18.0, 9.0}, "frames": 240.0,
			"pieces": []any{map[string]any{"splats": 300000.0}, map[string]any{"splats": 250000.0}}}}})
	if reef.Footprint["sizeM"] == nil || reef.Stats["pieces"] != 2 || reef.Stats["splats"] != 550000.0 || reef.Type != "" {
		t.Fatalf("%+v", reef)
	}
	if _, ok := reef.Brief.(Brief); !ok {
		t.Errorf("a reef's brief is %T", reef.Brief)
	}
}

func TestAVideoOfAStructureSaysWhatItIs(t *testing.T) {
	brief := Brief{Video: Video{ObjectID: "obj_1"}, Structure: &Structure{Type: "pipeline"}}
	if err := brief.Validate(); err != nil {
		t.Fatalf("a pipeline from a video was refused: %v", err)
	}
	brief.Structure.Type = "submarine"
	if err := brief.Validate(); err == nil {
		t.Fatal("a structure of no known type was taken")
	}
}
