package httpapi

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// A handler must be able to reach its own connection.
//
// Everything here is wrapped for logging, and a wrapper without Unwrap hides
// the connection from http.ResponseController: a handler asking to extend its
// write deadline is told the feature is not supported, and a slow one — like
// asking a model for a plan — has its connection closed under it with no
// reason the client can see.
func TestAHandlerCanStillReachItsOwnConnection(t *testing.T) {
	recorder := &statusRecorder{ResponseWriter: httptest.NewRecorder()}
	if under := recorder.Unwrap(); under == nil {
		t.Fatal("the recorder does not hand back what it wraps")
	}
	// httptest's recorder has no deadline to set, so what is checked here is
	// that the controller reaches through the wrapper at all rather than
	// stopping at it.
	if err := http.NewResponseController(recorder).SetWriteDeadline(time.Now().Add(time.Minute));
		err != nil && err.Error() == "feature not supported" {
		t.Fatal("the controller could not see past the recorder")
	}
}
