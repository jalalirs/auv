package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// readApprovals lists the addresses and domains an institution approves.
func (d *Dependencies) readApprovals(w http.ResponseWriter, r *http.Request) {
	approvals, err := d.Identity.Approvals(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"approvals": approvals})
}

type approveRequest struct {
	Email  string `json:"email"`
	Domain string `json:"domain"`
}

// approveEmail adds an address to an institution's list. Whoever signs in
// with it becomes a member and works on the institution's quota.
func (d *Dependencies) approveEmail(w http.ResponseWriter, r *http.Request) {
	var request approveRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	d.changeApprovals(w, r, policy.OrgAdminister, http.StatusCreated,
		func(conn db.Conn, orgID, actor string) (any, error) {
			return d.Identity.ApproveEmail(r.Context(), conn, orgID, request.Email, actor)
		}, map[string]any{"approvedEmail": request.Email})
}

// withdrawEmail takes an address off the list, and the membership with it.
func (d *Dependencies) withdrawEmail(w http.ResponseWriter, r *http.Request) {
	email := r.PathValue("email")
	d.changeApprovals(w, r, policy.OrgAdminister, http.StatusNoContent,
		func(conn db.Conn, orgID, _ string) (any, error) {
			return nil, d.Identity.WithdrawEmail(r.Context(), conn, orgID, email)
		}, map[string]any{"withdrawnEmail": email})
}

// approveDomain gives an institution a whole Workspace domain. Only the
// platform's administrator does this, so nobody claims a public domain.
func (d *Dependencies) approveDomain(w http.ResponseWriter, r *http.Request) {
	var request approveRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	d.changeApprovals(w, r, policy.PlatformAdminister, http.StatusCreated,
		func(conn db.Conn, orgID, actor string) (any, error) {
			return d.Identity.ApproveDomain(r.Context(), conn, orgID, request.Domain, actor)
		}, map[string]any{"approvedDomain": request.Domain})
}

// withdrawDomain takes a domain back from an institution.
func (d *Dependencies) withdrawDomain(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("domain")
	d.changeApprovals(w, r, policy.PlatformAdminister, http.StatusNoContent,
		func(conn db.Conn, orgID, _ string) (any, error) {
			return nil, d.Identity.WithdrawDomain(r.Context(), conn, orgID, name)
		}, map[string]any{"withdrawnDomain": name})
}

// changeApprovals makes one change to an institution's approvals and writes
// it down, in one transaction.
func (d *Dependencies) changeApprovals(w http.ResponseWriter, r *http.Request, action policy.Action,
	status int, change func(conn db.Conn, orgID, actor string) (any, error), detail map[string]any) {
	actor, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")
	var result any
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		if result, err = change(conn, orgID, actor.ID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(action), SubjectKind: "organisation",
			SubjectID: orgID, Outcome: audit.Succeeded, Detail: detail,
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	if status == http.StatusNoContent {
		w.WriteHeader(status)
		return
	}
	writeJSON(w, r, status, result.(identity.Approval))
}
