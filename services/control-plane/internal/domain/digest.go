package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
)

// DigestLength is the byte length of a SHA-256 digest.
const DigestLength = sha256.Size

// Digest is the content address of stored bytes. Identity is the digest, so it
// survives migration between one object store and another.
type Digest [DigestLength]byte

// ParseDigest reads a lower-case hexadecimal SHA-256 digest.
func ParseDigest(value string) (Digest, error) {
	var digest Digest
	if len(value) != hex.EncodedLen(DigestLength) {
		return digest, fmt.Errorf("%w: a digest is %d hexadecimal characters, got %d",
			ErrInvalid, hex.EncodedLen(DigestLength), len(value))
	}
	if value != strings.ToLower(value) {
		return digest, fmt.Errorf("%w: a digest is written in lower case", ErrInvalid)
	}
	raw, err := hex.DecodeString(value)
	if err != nil {
		return digest, fmt.Errorf("%w: %s", ErrInvalid, err)
	}
	copy(digest[:], raw)
	return digest, nil
}

// DigestFromBytes adopts an already-validated 32-byte digest.
func DigestFromBytes(raw []byte) (Digest, error) {
	var digest Digest
	if len(raw) != DigestLength {
		return digest, fmt.Errorf("%w: a digest is %d bytes, got %d", ErrInvalid, DigestLength, len(raw))
	}
	copy(digest[:], raw)
	return digest, nil
}

// String renders the digest as lower-case hexadecimal.
func (d Digest) String() string { return hex.EncodeToString(d[:]) }

// Bytes returns the digest as a slice for storage.
func (d Digest) Bytes() []byte { return d[:] }

// DigestOf is the digest of a run of bytes.
//
// Useful for identifying something the platform composed itself — a set of
// conditions, a canonical encoding — rather than something it was handed and
// must verify.
func DigestOf(content []byte) Digest { return Digest(sha256.Sum256(content)) }

// ManifestEntry is one file within a layer version's payload.
type ManifestEntry struct {
	RelativePath string
	Digest       Digest
	SizeBytes    int64
	MediaType    string
}

// ManifestDigest is the single citable identity of a multi-file version: the
// digest over every entry's path and content digest, in path order. Two
// versions with the same manifest digest contain exactly the same bytes under
// exactly the same names.
func ManifestDigest(entries []ManifestEntry) (Digest, error) {
	if len(entries) == 0 {
		return Digest{}, fmt.Errorf("%w: a version has at least one file", ErrInvalid)
	}
	ordered := make([]ManifestEntry, len(entries))
	copy(ordered, entries)
	sort.Slice(ordered, func(i, j int) bool {
		return ordered[i].RelativePath < ordered[j].RelativePath
	})

	hasher := sha256.New()
	previous := ""
	for _, entry := range ordered {
		if entry.RelativePath == previous {
			return Digest{}, fmt.Errorf("%w: %q appears twice in one manifest",
				ErrInvalid, entry.RelativePath)
		}
		previous = entry.RelativePath
		// Length-prefixing the path keeps the encoding unambiguous, so that no
		// two distinct manifests can hash alike.
		fmt.Fprintf(hasher, "%d:%s %s\n", len(entry.RelativePath), entry.RelativePath, entry.Digest)
	}
	return DigestFromBytes(hasher.Sum(nil))
}
