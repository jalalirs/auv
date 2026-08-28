package httpapi

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/city"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/layer"
	"github.com/jalalirs/auv/services/control-plane/internal/platform"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// Dependencies are the components the transport layer calls. Every one of them
// owns something; the transport owns none of it.
type Dependencies struct {
	Info       platform.Info
	Pool       *db.Pool
	Identity   *identity.Store
	Authorizer *policy.Authorizer
	Audit      *audit.Recorder
	Cities     *city.Store
	Layers     *layer.Store
	Objects    *storage.Objects
	Blobs      *storage.Blobs
	Broker     *exec.Broker
	Logger     *slog.Logger

	// LeaseDuration is how long a worker holds an attempt before it must
	// report in again.
	LeaseDuration time.Duration
	// SessionLifetime bounds how long one sign-in remains usable.
	SessionLifetime time.Duration
	// SecureCookies marks session cookies as requiring a secure transport,
	// which is correct everywhere the service is reached over TLS.
	SecureCookies bool
}

// authorize consults the decision point for a question a handler must ask
// beyond the one the router already asked, such as whether the caller may act
// on behalf of the organisation it named. It is the same decision point; there
// is no second one.
func (d *Dependencies) authorize(ctx context.Context, action policy.Action, resource policy.Resource) (policy.Decision, error) {
	subject, signedIn := subjectOf(ctx)
	if !signedIn {
		return policy.Decision{Effect: policy.EffectDenyHidden,
			Reason: "sign in to use this"}, nil
	}
	return d.Authorizer.Decide(ctx, subject, action, resource)
}

// requireOrg confirms the caller may act for the organisation it named, and
// reports the refusal itself if not.
func (d *Dependencies) requireOrg(w http.ResponseWriter, r *http.Request, orgID string) bool {
	decision, err := d.authorize(r.Context(), policy.OrgRead, policy.Org(orgID))
	if err != nil {
		writeError(w, r, err)
		return false
	}
	if !decision.Allowed() {
		writeDenied(w, r, decision)
		return false
	}
	return true
}
