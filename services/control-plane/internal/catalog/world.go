package catalog

import (
	"encoding/json"
	"fmt"
	"math"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// A world's document: one scene of layers, each pointing at library assets,
// and the package version it was baked into for the simulator. The format is
// written down in docs/plan/world-document.md.

// WorldFormat is what a world document says it is.
const WorldFormat = "world/1"

// WorldLayerKinds are the layers a world is made of.
var WorldLayerKinds = map[string]bool{
	"water": true, "terrain": true, "seabed": true, "reef": true,
	"structures": true, "life": true,
}

// WorldDocument is the part of a world document the platform reads; the rest
// is the editor's and is kept as written.
type WorldDocument struct {
	Format string `json:"iocean"`
	Name   string `json:"name"`
	Frame  struct {
		ExtentM [2]float64 `json:"extentM"`
	} `json:"frame"`
	Georef *struct {
		Origin struct {
			Lat float64 `json:"lat"`
			Lon float64 `json:"lon"`
		} `json:"origin"`
	} `json:"georef"`
	Layers []WorldLayer `json:"layers"`
	// Bake is the package a dive in this world runs in.
	Bake *struct {
		Version string `json:"version"`
	} `json:"bake"`
}

// WorldLayer is one layer: its kind, and for structures the things in it.
type WorldLayer struct {
	ID    string            `json:"id"`
	Kind  string            `json:"kind"`
	Items []json.RawMessage `json:"items,omitempty"`
	// Params a reef says of itself; a big reef's says its items are edits
	// over the build they were made on: its colonies file's digest, and the
	// package it came in, for people.
	Params *struct {
		ColonyEdits bool   `json:"colonyEdits,omitempty"`
		EditedOn    string `json:"editedOn,omitempty"`
		Digest      string `json:"digest,omitempty"`
	} `json:"params,omitempty"`
}

// ValidateWorld refuses a document the platform could not bake or fly.
func ValidateWorld(document json.RawMessage) error {
	var world WorldDocument
	if err := json.Unmarshal(document, &world); err != nil {
		return fmt.Errorf("%w: a world document is JSON: %v", domain.ErrInvalid, err)
	}
	if world.Format != WorldFormat {
		return fmt.Errorf("%w: a world document says \"iocean\": %q", domain.ErrInvalid, WorldFormat)
	}
	for _, v := range world.Frame.ExtentM {
		if math.IsNaN(v) || v <= 0 || v > 1e6 {
			return fmt.Errorf("%w: a world's frame has an extent in metres, more than 0", domain.ErrInvalid)
		}
	}
	if world.Georef != nil {
		o := world.Georef.Origin
		if o.Lat < -90 || o.Lat > 90 || o.Lon < -180 || o.Lon > 180 {
			return fmt.Errorf("%w: a world's georeference is latitude, longitude in degrees", domain.ErrInvalid)
		}
	}
	seen := map[string]bool{}
	for _, layer := range world.Layers {
		if !WorldLayerKinds[layer.Kind] {
			return fmt.Errorf("%w: a world has no %q layer", domain.ErrInvalid, layer.Kind)
		}
		if layer.ID == "" || seen[layer.ID] {
			return fmt.Errorf("%w: every layer has its own id", domain.ErrInvalid)
		}
		seen[layer.ID] = true
		ids := map[string]bool{}
		for i, raw := range layer.Items {
			var item struct {
				ID string `json:"id"`
			}
			if json.Unmarshal(raw, &item) != nil || item.ID == "" || ids[item.ID] {
				return fmt.Errorf("%w: item %d of layer %q has no id of its own", domain.ErrInvalid, i, layer.ID)
			}
			ids[item.ID] = true
		}
	}
	return nil
}

// WorldThings writes a world's structures as the layout the simulator reads:
// {"version": ..., "things": [...]}. A structures item is a thing already,
// except an object: a model from the library, laid into the package's own
// seabed when the world is baked, and drawn from there.
func WorldThings(versionID string, document json.RawMessage) (json.RawMessage, error) {
	var world WorldDocument
	if err := json.Unmarshal(document, &world); err != nil {
		return nil, fmt.Errorf("reading a world document: %w", err)
	}
	things := []json.RawMessage{}
	for _, layer := range world.Layers {
		if layer.Kind != "structures" {
			continue
		}
		for _, raw := range layer.Items {
			var item struct {
				Kind string `json:"kind"`
			}
			if json.Unmarshal(raw, &item) == nil && item.Kind != "object" {
				things = append(things, raw)
			}
		}
	}
	return json.Marshal(map[string]any{"version": versionID, "things": things})
}

// WorldColonies writes a world's reef as the runtime reads it in the brief:
// {"version": ..., "items": [...]}, the coral items of its reef layers as they
// are. A world whose reef has no coral items (one never opened in the editor,
// or one with more colonies than the editor holds) gives nil, and the dive
// keeps the build's colonies: an empty list would say every one was gone.
func WorldColonies(versionID string, document json.RawMessage) (json.RawMessage, error) {
	var world WorldDocument
	if err := json.Unmarshal(document, &world); err != nil {
		return nil, fmt.Errorf("reading a world document: %w", err)
	}
	items := []json.RawMessage{}
	partial, editedOn, digest := false, "", ""
	for _, layer := range world.Layers {
		if layer.Kind != "reef" {
			continue
		}
		if layer.Params != nil && layer.Params.ColonyEdits {
			partial, editedOn, digest = true, layer.Params.EditedOn, layer.Params.Digest
		}
		for _, raw := range layer.Items {
			var item struct {
				Kind string `json:"kind"`
			}
			if json.Unmarshal(raw, &item) == nil && item.Kind == "coral" {
				items = append(items, raw)
			}
		}
	}
	if len(items) == 0 {
		return nil, nil
	}
	// A big reef's are only the colonies changed, on the build they were
	// changed on; the rest stay as built, and a dive on another build (its
	// colonies file of another digest) takes none.
	if partial {
		return json.Marshal(map[string]any{"version": versionID, "partial": true, "digest": digest, "package": editedOn, "items": items})
	}
	return json.Marshal(map[string]any{"version": versionID, "items": items})
}

// WorldBake is the package version a world document was baked into, or "".
func WorldBake(document json.RawMessage) string {
	var world WorldDocument
	if json.Unmarshal(document, &world) != nil || world.Bake == nil {
		return ""
	}
	return world.Bake.Version
}
