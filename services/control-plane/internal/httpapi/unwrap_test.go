package httpapi

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// A writer that can have its deadline set, which a real connection can and
// httptest's recorder cannot — so that what is tested here is the wrapper and
// not the standard library.
type withDeadline struct {
	http.ResponseWriter
	asked time.Time
}

func (d *withDeadline) SetWriteDeadline(at time.Time) error {
	d.asked = at
	return nil
}

// A handler must be able to reach its own connection.
//
// Everything here is wrapped for logging, and a wrapper without Unwrap hides
// the connection from http.ResponseController: a handler asking to extend its
// write deadline is told the feature is not supported, and a slow one — like
// asking a model for a plan — has its connection closed under it at thirty
// seconds with no reason the client can see. That is not a hypothetical; it
// is what drafting did until this existed.
func TestAHandlerCanStillReachItsOwnConnection(t *testing.T) {
	connection := &withDeadline{ResponseWriter: httptest.NewRecorder()}
	recorder := &statusRecorder{ResponseWriter: connection}

	until := time.Now().Add(4 * time.Minute)
	if err := http.NewResponseController(recorder).SetWriteDeadline(until); err != nil {
		t.Fatalf("the controller could not see past the recorder: %v", err)
	}
	if !connection.asked.Equal(until) {
		t.Fatal("the deadline never reached the connection")
	}
}
