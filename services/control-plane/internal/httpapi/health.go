package httpapi

import (
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
)

// live reports that the process can serve HTTP. It deliberately depends on
// nothing else, so that a database outage does not cause the process to be
// restarted when restarting it would not help.
func (d *Dependencies) live(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, r, http.StatusOK, map[string]any{"status": "live"})
}

// ready reports that the platform can do its work: the record is reachable,
// the schema is the one this build expects, and stored bytes can be reached.
//
// A build whose migrations have not been applied is deliberately not ready,
// because serving against an older schema would write records this build's
// rules were never checked against.
func (d *Dependencies) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := contextWithTimeout(r, 3*time.Second)
	defer cancel()

	checks := map[string]any{}
	ready := true

	if err := d.Pool.Ping(ctx); err != nil {
		checks["record"] = err.Error()
		ready = false
	} else {
		checks["record"] = "reachable"
		pending, err := db.PendingMigrations(ctx, d.Pool)
		switch {
		case err != nil:
			checks["schema"] = err.Error()
			ready = false
		case len(pending) > 0:
			checks["schema"] = "migrations this build carries have not been applied"
			checks["pendingMigrations"] = pending
			ready = false
		default:
			checks["schema"] = "current"
		}
	}

	if err := d.Blobs.Reachable(ctx); err != nil {
		checks["storage"] = err.Error()
		ready = false
	} else {
		checks["storage"] = "reachable"
	}

	status := http.StatusOK
	if !ready {
		status = http.StatusServiceUnavailable
	}
	writeJSON(w, r, status, map[string]any{"ready": ready, "checks": checks})
}

// platformInfo reports the build serving this request, which is what makes a
// deployment identifiable without shell access.
func (d *Dependencies) platformInfo(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, r, http.StatusOK, d.Info)
}
