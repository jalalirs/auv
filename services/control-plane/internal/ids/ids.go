// Package ids issues identifiers that say what they are.
//
// An identifier carries a kind prefix and a lexicographically sortable body.
// The prefix makes a mistyped reference a compile-time or validation failure
// rather than a silent lookup miss; the sortable body means identifiers order
// by creation time without a separate column.
package ids

import (
	"crypto/rand"
	"encoding/binary"
	"errors"
	"fmt"
	"strings"
	"time"
)

// Kind names the sort of object an identifier refers to.
type Kind string

const (
	KindOrganisation Kind = "org"
	KindPrincipal    Kind = "prin"
	KindCredential   Kind = "cred"
	KindSession      Kind = "sess"
	KindBinding      Kind = "bind"
	KindDenial       Kind = "deny"
	KindAuditEvent   Kind = "aud"
	KindObject       Kind = "obj"
	KindUploadGrant  Kind = "upl"
	KindCity         Kind = "city"
	KindLayer        Kind = "layer"
	KindVersion      Kind = "ver"
	KindTarget       Kind = "tgt"
	KindJob          Kind = "job"
	KindAttempt      Kind = "att"
	KindJobEvent     Kind = "evt"
	KindAdmission    Kind = "adm"
	KindRefusal      Kind = "ref"
	KindSchedule     Kind = "sch"

	// The dive domain. A city and a package version keep the kinds they
	// already had, because they are the same idea told properly.
	KindVehicle    Kind = "veh"
	KindQueue      Kind = "queue"
	KindDevice     Kind = "dev"
	KindStack      Kind = "stack"
	KindConditions Kind = "cond"
	KindDive       Kind = "dive"
	KindRun        Kind = "run"
)

var kinds = map[Kind]struct{}{
	KindOrganisation: {}, KindPrincipal: {}, KindCredential: {}, KindSession: {},
	KindBinding: {}, KindDenial: {}, KindAuditEvent: {}, KindObject: {},
	KindUploadGrant: {}, KindCity: {}, KindLayer: {}, KindVersion: {},
	KindTarget: {}, KindJob: {}, KindAttempt: {}, KindJobEvent: {},
	KindAdmission: {}, KindRefusal: {}, KindSchedule: {},
	KindVehicle: {}, KindQueue: {}, KindDevice: {}, KindStack: {},
	KindConditions: {}, KindDive: {}, KindRun: {},
}

// ErrMalformed reports an identifier that is not of the expected shape or kind.
var ErrMalformed = errors.New("malformed identifier")

// crockford is Crockford base32: no I, L, O, or U, so an identifier read aloud
// or copied by hand does not become a different identifier.
const crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

const bodyLength = 26

// New returns a fresh identifier of the given kind.
func New(kind Kind) string {
	return newAt(kind, time.Now())
}

func newAt(kind Kind, at time.Time) string {
	var raw [16]byte
	binary.BigEndian.PutUint64(raw[:8], uint64(at.UnixMilli())<<16)
	if _, err := rand.Read(raw[6:]); err != nil {
		// crypto/rand does not fail on any supported platform; if it ever
		// does, issuing a predictable identifier would be worse than stopping.
		panic(fmt.Sprintf("ids: no randomness available: %v", err))
	}
	return string(kind) + "_" + encode(raw)
}

// encode writes the 128 bits as 26 base32 symbols, least significant last, so
// that identifiers sort in the same order as the timestamps they begin with.
func encode(raw [16]byte) string {
	var out [bodyLength]byte
	value := new(uint128).fromBytes(raw)
	for pos := bodyLength - 1; pos >= 0; pos-- {
		out[pos] = crockford[value.shiftOutFive()]
	}
	return string(out[:])
}

// uint128 supports the shift-out needed to base32-encode 16 bytes without an
// external dependency.
type uint128 struct{ hi, lo uint64 }

func (u *uint128) fromBytes(raw [16]byte) *uint128 {
	u.hi = binary.BigEndian.Uint64(raw[0:8])
	u.lo = binary.BigEndian.Uint64(raw[8:16])
	return u
}

func (u *uint128) shiftOutFive() byte {
	out := byte(u.lo & 0x1f)
	u.lo = (u.lo >> 5) | (u.hi << 59)
	u.hi >>= 5
	return out
}

// Parse validates an identifier and confirms it names the expected kind.
func Parse(kind Kind, value string) (string, error) {
	if _, ok := kinds[kind]; !ok {
		return "", fmt.Errorf("%w: unknown kind %q", ErrMalformed, kind)
	}
	prefix := string(kind) + "_"
	if !strings.HasPrefix(value, prefix) {
		return "", fmt.Errorf("%w: %q is not a %s identifier", ErrMalformed, value, kind)
	}
	body := value[len(prefix):]
	if len(body) != bodyLength {
		return "", fmt.Errorf("%w: %q has a %d-symbol body, expected %d",
			ErrMalformed, value, len(body), bodyLength)
	}
	for _, symbol := range body {
		if !strings.ContainsRune(crockford, symbol) {
			return "", fmt.Errorf("%w: %q contains %q", ErrMalformed, value, symbol)
		}
	}
	return value, nil
}

// KindOf reports the kind an identifier claims, without validating its body.
func KindOf(value string) (Kind, bool) {
	name, _, found := strings.Cut(value, "_")
	if !found {
		return "", false
	}
	kind := Kind(name)
	_, known := kinds[kind]
	return kind, known
}
