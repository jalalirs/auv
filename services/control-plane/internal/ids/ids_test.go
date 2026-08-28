package ids

import (
	"errors"
	"sort"
	"testing"
	"time"
)

func TestAnIdentifierSaysWhatItIs(t *testing.T) {
	id := New(KindCity)
	if _, err := Parse(KindCity, id); err != nil {
		t.Fatalf("Parse(city, %q) error = %v", id, err)
	}
	// A city identifier is not a job identifier, and using one where the other
	// belongs is a refusal rather than a lookup that quietly finds nothing.
	if _, err := Parse(KindJob, id); !errors.Is(err, ErrMalformed) {
		t.Fatalf("a city identifier was accepted as a job identifier: %v", err)
	}
}

func TestIdentifiersOrderByWhenTheyWereIssued(t *testing.T) {
	// Sortability is what lets a listing be ordered by creation without a
	// separate column, so it is worth asserting rather than assuming.
	var issued []string
	for i := 0; i < 8; i++ {
		issued = append(issued, newAt(KindJob, time.UnixMilli(int64(1_700_000_000_000+i*1000))))
	}
	sorted := make([]string, len(issued))
	copy(sorted, issued)
	sort.Strings(sorted)

	for i := range issued {
		if issued[i] != sorted[i] {
			t.Fatalf("identifiers do not sort by issue time:\n  issued: %v\n  sorted: %v",
				issued, sorted)
		}
	}
}

func TestIdentifiersAreDistinct(t *testing.T) {
	seen := make(map[string]struct{}, 4096)
	for i := 0; i < 4096; i++ {
		id := New(KindObject)
		if _, repeated := seen[id]; repeated {
			t.Fatalf("issued %q twice", id)
		}
		seen[id] = struct{}{}
	}
}

func TestAMalformedIdentifierIsRefused(t *testing.T) {
	refused := []string{
		"", "city", "city_", "city_tooshort",
		"city_0123456789012345678901234U", // U is excluded: it reads as V
		"unknown_01ARZ3NDEKTSV4RRFFQ69G5FAV",
	}
	for _, value := range refused {
		if _, err := Parse(KindCity, value); err == nil {
			t.Errorf("Parse(city, %q) accepted a malformed identifier", value)
		}
	}
}

func TestKindOfReadsThePrefix(t *testing.T) {
	kind, known := KindOf(New(KindVersion))
	if !known || kind != KindVersion {
		t.Fatalf("KindOf() = %q, %v; want version, true", kind, known)
	}
	if _, known := KindOf("nonsense"); known {
		t.Fatal("KindOf() recognised a value with no kind prefix")
	}
}
