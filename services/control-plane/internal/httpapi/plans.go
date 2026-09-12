package httpapi

import (
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/planning"
)

// How long drafting may take. Far longer than anything else this service does,
// and deliberately so: a model that reasons before it answers thinks for the
// better part of a minute, and the server's ordinary write timeout — thirty
// seconds, which is generous for a database query — cuts the connection while
// the model is still thinking. The client then sees a dead socket and no
// reason for it.
//
// Extended for this route alone rather than raised for the whole server: every
// other request here should still be fast, and a slow dependency behind one of
// them is a fault rather than a feature.
const draftingTakes = 4 * time.Minute

// Drafting a plan from words.
//
// The words go up and the plan comes back, because the key that reaches a
// model must not reach a console: an application somebody installs cannot be
// given a secret. What returns has been checked against what the vehicle can
// actually fly, so that a plan nobody can follow is refused here rather than
// discovered halfway through a dive.

type draftPlanRequest struct {
	Said string `json:"said"`
	// Where the vehicle will be when it is asked. A plan is written in the
	// world's coordinates, and an instruction like "two hundred metres north"
	// is not, so the drafting needs somewhere to start from.
	From planning.From `json:"from"`
	// What the vehicle can be asked to do, as its package states it. Sent by
	// whoever is composing the dive, because they have chosen the vehicle and
	// hold its package; the platform does the checking, because a limit
	// enforced only by the thing that wants to exceed it is not a limit.
	Envelope planning.Envelope `json:"envelope"`
}

func (d *Dependencies) draftPlan(w http.ResponseWriter, r *http.Request) {
	var request draftPlanRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if len(request.Said) == 0 {
		writeJSON(w, r, http.StatusOK, planning.Read{
			Why: "nothing was asked for",
		})
		return
	}
	// The connection must outlive the thinking.
	if err := http.NewResponseController(w).SetWriteDeadline(time.Now().Add(draftingTakes)); err != nil {
		d.Logger.Warn("could not extend the deadline for drafting", "error", err)
	}
	asking, stop := contextWithTimeout(r, draftingTakes)
	defer stop()
	read, err := d.Drafter.Draft(asking, request.Said, request.From, request.Envelope)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// Always an answer, never an error: a plan that could not be drafted is a
	// normal outcome with a reason, and the console shows the reason. The only
	// errors here are the platform's own.
	writeJSON(w, r, http.StatusOK, read)
}
