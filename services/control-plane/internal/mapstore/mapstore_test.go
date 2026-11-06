package mapstore

import (
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

func TestACardShowsWhatThePlaceSaysOfItself(t *testing.T) {
	look := lookOf(map[string]any{
		"deepestM": 31.0, "shallowestM": 0.4,
		"from": map[string]any{"surveyed": false, "surveyedFraction": nil, "method": "Sentinel-2, Stumpf",
			"depth": map[string]any{"sources": []any{}}},
		"reef": map[string]any{"colonies": 2400000.0},
	}, []catalog.File{{Path: "site.json", ObjectID: "obj_s"}, {Path: "picture.jpg", ObjectID: "obj_p"}})
	if *look.DeepestM != 31 || *look.Surveyed || look.SurveyedFraction != nil || *look.Colonies != 2400000 {
		t.Fatalf("%+v", look)
	}
	if look.Picture == nil || look.Picture.ObjectID != "obj_p" || look.Depth == nil || look.Method == "" {
		t.Fatalf("%+v", look)
	}
	if empty := lookOf(nil, nil); empty.DeepestM != nil || empty.Picture != nil {
		t.Fatalf("a place with no record showed %+v", empty)
	}
}

func TestOnlyPlacesThatShareGroundWithTheAreaAreOffered(t *testing.T) {
	alFahal := domain.Extent{West: 38.947, South: 22.270, East: 38.977, North: 22.298}
	if !overlaps(alFahal, Square{Lat: 22.284, Lon: 38.962, AcrossM: 500}) {
		t.Error("an area in the middle of Al Fahal does not overlap it")
	}
	if !overlaps(alFahal, Square{Lat: 22.300, Lon: 38.980, AcrossM: 1000}) {
		t.Error("an area over Al Fahal's corner does not overlap it")
	}
	if overlaps(alFahal, Square{Lat: 22.40, Lon: 38.96, AcrossM: 1000}) {
		t.Error("an area 12 km north overlaps Al Fahal")
	}
	if overlaps(domain.Extent{}, Square{Lat: 0, Lon: 0, AcrossM: 1000}) {
		t.Error("a place with no extent overlaps the area at 0, 0")
	}
	near := distanceM(alFahal, Square{Lat: 22.284, Lon: 38.962})
	far := distanceM(alFahal, Square{Lat: 22.300, Lon: 38.980})
	if near > 10 || far < 2000 || far > 3000 {
		t.Errorf("distances %v and %v", near, far)
	}
}

func TestAnOrganisationsPlaceIsInTheStoreOnlyWhileOffered(t *testing.T) {
	ours := catalog.City{OwnedByOrg: "org_a", Discoverable: true}
	if Listed(ours) {
		t.Fatal("an organisation's place was listed without being offered")
	}
	ours.InStore = true
	if !Listed(ours) {
		t.Fatal("an offered place was not listed")
	}
	if !Listed(catalog.City{Discoverable: true}) || Listed(catalog.City{}) {
		t.Fatal("the store's own places are its discoverable ones")
	}
}
