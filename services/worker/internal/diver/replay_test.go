package diver

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

// The commands a film replays land where the brief says they are, in a
// directory made for them; a URL that does not serve them is a failure, not
// an empty file the runtime would play back as a vehicle let go.
func TestTheReplayIsFetchedBesideTheBrief(t *testing.T) {
	served := []byte("\x93NUMPY fake")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/commands.npy" {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write(served)
	}))
	defer server.Close()

	into := filepath.Join(t.TempDir(), "replay", "commands.npy")
	if err := fetchTo(context.Background(), server.URL+"/commands.npy", into); err != nil {
		t.Fatalf("fetching: %v", err)
	}
	got, err := os.ReadFile(into)
	if err != nil || string(got) != string(served) {
		t.Fatalf("wrote %q, %v", got, err)
	}
	if err := fetchTo(context.Background(), server.URL+"/nothing", into+".missing"); err == nil {
		t.Fatal("a 404 was taken for the commands")
	}
}
