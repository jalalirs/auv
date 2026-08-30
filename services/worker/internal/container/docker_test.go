package container

import (
	"encoding/binary"
	"testing"
)

// The runtime frames a container's output when no terminal is attached. What
// the record keeps must be what the program actually wrote, not the framing
// around it.
func TestContainerOutputIsUnframed(t *testing.T) {
	frame := func(stream byte, payload string) []byte {
		header := make([]byte, 8)
		header[0] = stream
		binary.BigEndian.PutUint32(header[4:], uint32(len(payload)))
		return append(header, payload...)
	}

	raw := append(frame(1, "reading soundings\n"), frame(2, "warning: one frame skipped\n")...)
	if got := demultiplex(raw); got != "reading soundings\nwarning: one frame skipped\n" {
		t.Fatalf("demultiplex() = %q", got)
	}
}

func TestUnframedOutputIsLeftAlone(t *testing.T) {
	// A container with a terminal attached is not framed at all.
	if got := demultiplex([]byte("plain output")); got != "plain output" {
		t.Fatalf("demultiplex() = %q, want the text unchanged", got)
	}
}

func TestATruncatedFrameDoesNotReadPastItsEnd(t *testing.T) {
	header := make([]byte, 8)
	binary.BigEndian.PutUint32(header[4:], 1000)
	raw := append(header, []byte("short")...)
	if got := demultiplex(raw); got != "short" {
		t.Fatalf("demultiplex() = %q, want the bytes that were actually there", got)
	}
}

// Hosts in this platform's own deployment run runtimes several releases apart,
// so the version is negotiated. Comparing versions wrongly would pin the wrong
// one and fail on one host or the other.
func TestInterfaceVersionsCompareCorrectly(t *testing.T) {
	cases := []struct {
		candidate, reference string
		older                bool
	}{
		{"1.43", "1.44", true},
		{"1.44", "1.44", false},
		{"1.47", "1.44", false},
		{"1.9", "1.44", true},
		{"2.0", "1.44", false},
		{"1.100", "1.44", false},
	}
	for _, test := range cases {
		if got := olderThan(test.candidate, test.reference); got != test.older {
			t.Errorf("olderThan(%q, %q) = %v, want %v",
				test.candidate, test.reference, got, test.older)
		}
	}
}

// Calls must not be made before a version has been agreed, because an
// unversioned call means whatever the daemon decides it means.
func TestNoCallIsMadeBeforeAVersionIsAgreed(t *testing.T) {
	runtime := Open("/nonexistent.sock")
	if _, err := runtime.Create(t.Context(), Spec{}); err == nil {
		t.Fatal("a call was attempted before any version was agreed")
	}
}

// What a dive is attached to is the whole of what it can reach, so it is worth
// checking rather than assuming. The two halves of a dive go on a network made
// for that dive; everything else goes on none.
func TestWorkGoesOnTheNetworkItWasGiven(t *testing.T) {
	networkOf := func(spec Spec) string {
		host := createRequest(spec)["HostConfig"].(map[string]any)
		return host["NetworkMode"].(string)
	}

	if got := networkOf(Spec{Image: "x"}); got != "none" {
		t.Errorf("work granted no network went on %q, and should have gone nowhere", got)
	}
	if got := networkOf(Spec{Image: "x", Attach: "coral-dive-run_1"}); got != "coral-dive-run_1" {
		t.Errorf("a dive went on %q rather than its own network", got)
	}
	// Attaching wins over the general grant: a dive that also carried the
	// network capability must still be confined to its own network, not put on
	// the host's bridge beside everything else on the machine.
	if got := networkOf(Spec{Image: "x", Network: true, Attach: "coral-dive-run_1"}); got != "coral-dive-run_1" {
		t.Errorf("a dive with the network capability went on %q, escaping its own network", got)
	}
}
