package reconstructing

import "testing"

func height(m float64) *float64 { return &m }

func TestABriefNamesAVideoAndSaysNothingImpossible(t *testing.T) {
	good := Brief{Video: Video{ObjectID: "obj_1", Name: "GX010.MP4"}}
	if err := good.Validate(); err != nil {
		t.Fatalf("a video and nothing else: %v", err)
	}
	full := Brief{Video: Video{ObjectID: "obj_1"}, CameraHeightM: height(1.5),
		Start: &Point{Lat: 22.3, Lon: 38.9}, FPS: 3, Tape: "keep"}
	if err := full.Validate(); err != nil {
		t.Fatalf("everything said, all of it possible: %v", err)
	}
	cases := map[string]Brief{
		"no video":                    {},
		"a camera on the reef":        {Video: Video{ObjectID: "obj_1"}, CameraHeightM: height(0.2)},
		"a camera far above the reef": {Video: Video{ObjectID: "obj_1"}, CameraHeightM: height(25)},
		"a start off the Earth":       {Video: Video{ObjectID: "obj_1"}, Start: &Point{Lat: 91, Lon: 0}},
		"a start past the dateline":   {Video: Video{ObjectID: "obj_1"}, Start: &Point{Lat: 0, Lon: 181}},
		"too few frames":              {Video: Video{ObjectID: "obj_1"}, FPS: 0.1},
		"too many frames":             {Video: Video{ObjectID: "obj_1"}, FPS: 30},
		"a tape of no kind":           {Video: Video{ObjectID: "obj_1"}, Tape: "remove"},
	}
	for name, brief := range cases {
		if brief.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
}

func TestAVideoIsKnownByItsTypeOrItsName(t *testing.T) {
	cases := []struct {
		media, name string
		video       bool
	}{
		{"video/mp4", "", true},
		{"application/octet-stream", "GX010123.MP4", true},
		{"application/octet-stream", "dive.mov", true},
		{"application/octet-stream", "dive.MKV", true},
		{"application/octet-stream", "depths.tif", false},
		{"image/jpeg", "frame.jpg", false},
	}
	for _, c := range cases {
		if got := isVideo(c.media, c.name); got != c.video {
			t.Errorf("isVideo(%q, %q) = %v", c.media, c.name, got)
		}
	}
}

func TestTheJobFindsTheVideoUnderItsOwnSafeName(t *testing.T) {
	cases := map[string]string{
		"GX010.MP4":        "video/GX010.MP4",
		"../../etc/passwd": "video/passwd",
		"my dive (1).mov":  "video/my_dive_1_.mov",
		"":                 "video/video.mp4",
		"..":               "video/video.mp4",
	}
	for name, want := range cases {
		if got := pathOf(name, "video/mp4"); got != want {
			t.Errorf("pathOf(%q) = %q, want %q", name, got, want)
		}
	}
	if got := pathOf("", "video/quicktime"); got != "video/video.mov" {
		t.Errorf("an unnamed QuickTime video is at %q", got)
	}
}

func TestAReconstructionIsCalledByItsLabelOrItsVideo(t *testing.T) {
	if got := nameOf(Brief{Label: "Al Fahal north", Video: Video{Path: "video/GX010.MP4"}}); got != "Al Fahal north" {
		t.Errorf("labelled: %q", got)
	}
	if got := nameOf(Brief{Video: Video{Path: "video/GX010.MP4"}}); got != "GX010" {
		t.Errorf("unlabelled: %q", got)
	}
}

func TestTheManifestMustNameOnlyWhatThePackageHolds(t *testing.T) {
	raw := []byte(`{"name": "x", "frames": 120, "registered": 118,
		"pieces": [{"part": "parts/part-1.usdz", "checkpoint": "parts/part-1.pt", "first": 0, "last": 60, "splats": 400000}],
		"extentM": [12.5, NaN], "scale": {"factor": 1.0, "how": "assumed", "from": "camera height 1.92 m"},
		"surface": {"file": "surface.f32", "rows": 10, "columns": 10, "cellM": 0.1, "origin": [0, 0]},
		"path": "path.json", "preview": "preview.jpg"}`)
	record, err := readManifest(raw)
	if err != nil {
		t.Fatalf("a manifest with NaN in it: %v", err)
	}
	held := map[string]bool{"reconstruction.json": true, "parts/part-1.usdz": true, "parts/part-1.pt": true,
		"surface.f32": true, "surface.json": true, "path.json": true, "preview.jpg": true}
	if err := checkManifest(record, held); err != nil {
		t.Fatalf("a whole package: %v", err)
	}
	for _, missing := range []string{"parts/part-1.usdz", "parts/part-1.pt", "surface.f32", "path.json", "preview.jpg"} {
		without := map[string]bool{}
		for k := range held {
			if k != missing {
				without[k] = true
			}
		}
		if checkManifest(record, without) == nil {
			t.Errorf("a package without %s was accepted", missing)
		}
	}
	if err := checkManifest(map[string]any{"name": "x"}, held); err == nil {
		t.Error("a manifest with no pieces was accepted")
	}
	if _, err := readManifest([]byte(`[1, 2]`)); err == nil {
		t.Error("a manifest that is not an object was read")
	}
}
