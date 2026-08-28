package domain

import (
	"crypto/sha256"
	"strings"
	"testing"
)

func digestOf(content string) Digest {
	sum := sha256.Sum256([]byte(content))
	digest, err := DigestFromBytes(sum[:])
	if err != nil {
		panic(err)
	}
	return digest
}

func TestADigestRoundTripsThroughText(t *testing.T) {
	original := digestOf("bathymetry")
	parsed, err := ParseDigest(original.String())
	if err != nil {
		t.Fatalf("ParseDigest() error = %v", err)
	}
	if parsed != original {
		t.Fatal("a digest did not survive being written and read")
	}
}

func TestAMalformedDigestIsRefused(t *testing.T) {
	refused := []string{
		"", "abc",
		strings.Repeat("g", 64),                 // not hexadecimal
		strings.ToUpper(digestOf("x").String()), // upper case
		digestOf("x").String() + "0",            // too long
	}
	for _, value := range refused {
		if _, err := ParseDigest(value); err == nil {
			t.Errorf("ParseDigest(%q) accepted a malformed digest", value)
		}
	}
}

// A version's identity is the digest over its whole manifest, so that a
// multi-file payload has one citable content address.
func TestAManifestDigestCoversEveryFile(t *testing.T) {
	base := []ManifestEntry{
		{RelativePath: "tileset.json", Digest: digestOf("a")},
		{RelativePath: "tiles/0.b3dm", Digest: digestOf("b")},
	}
	first, err := ManifestDigest(base)
	if err != nil {
		t.Fatalf("ManifestDigest() error = %v", err)
	}

	// Order of presentation must not change identity: the same files are the
	// same version however they were listed.
	reordered := []ManifestEntry{base[1], base[0]}
	second, err := ManifestDigest(reordered)
	if err != nil {
		t.Fatalf("ManifestDigest() error = %v", err)
	}
	if first != second {
		t.Fatal("reordering the manifest changed the version's identity")
	}

	// Changing any file's content changes the version.
	changed := []ManifestEntry{
		{RelativePath: "tileset.json", Digest: digestOf("a")},
		{RelativePath: "tiles/0.b3dm", Digest: digestOf("different")},
	}
	third, err := ManifestDigest(changed)
	if err != nil {
		t.Fatalf("ManifestDigest() error = %v", err)
	}
	if first == third {
		t.Fatal("changing a file left the version's identity unchanged")
	}

	// Moving a file changes the version too, because the payload is the paths
	// as much as the bytes.
	moved := []ManifestEntry{
		{RelativePath: "tileset.json", Digest: digestOf("a")},
		{RelativePath: "tiles/1.b3dm", Digest: digestOf("b")},
	}
	fourth, err := ManifestDigest(moved)
	if err != nil {
		t.Fatalf("ManifestDigest() error = %v", err)
	}
	if first == fourth {
		t.Fatal("moving a file left the version's identity unchanged")
	}
}

func TestAManifestCannotBeEmptyOrRepeatAPath(t *testing.T) {
	if _, err := ManifestDigest(nil); err == nil {
		t.Fatal("a version with no files was given an identity")
	}
	duplicate := []ManifestEntry{
		{RelativePath: "same", Digest: digestOf("a")},
		{RelativePath: "same", Digest: digestOf("b")},
	}
	if _, err := ManifestDigest(duplicate); err == nil {
		t.Fatal("a manifest naming one path twice was accepted")
	}
}
