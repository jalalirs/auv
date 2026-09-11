package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/planning"
)

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
	read, err := d.Drafter.Draft(r.Context(), request.Said, request.From)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// Always an answer, never an error: a plan that could not be drafted is a
	// normal outcome with a reason, and the console shows the reason. The only
	// errors here are the platform's own.
	writeJSON(w, r, http.StatusOK, read)
}
