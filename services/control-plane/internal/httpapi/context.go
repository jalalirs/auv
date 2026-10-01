package httpapi

import (
	"context"

	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
)

type contextKey int

const (
	decisionKey contextKey = iota
	principalKey
	viaTokenKey
)

// caller is the authenticated actor together with what the decision point
// needs to reason about it.
type caller struct {
	Principal identity.Principal
	Subject   policy.Subject
	// ViaToken is set when the person is acting through a token they made for
	// a program, rather than having signed in themselves. Everything they may
	// do they may do this way, except make or revoke tokens: a token that
	// could mint another would let a leaked one outlive being revoked.
	ViaToken bool
}

func withCaller(ctx context.Context, who caller) context.Context {
	ctx = context.WithValue(ctx, principalKey, who.Principal)
	ctx = context.WithValue(ctx, viaTokenKey, who.ViaToken)
	return reqctx.WithSubject(ctx, who.Subject)
}

// viaToken reports whether the caller came in through a personal token.
func viaToken(ctx context.Context) bool {
	via, _ := ctx.Value(viaTokenKey).(bool)
	return via
}

// subjectOf returns the authenticated subject, if the request carried one.
func subjectOf(ctx context.Context) (policy.Subject, bool) {
	raw, present := reqctx.RawSubject(ctx)
	if !present {
		return policy.Subject{}, false
	}
	subject, ok := raw.(policy.Subject)
	return subject, ok
}

// principalOf returns the authenticated principal, if the request carried one.
func principalOf(ctx context.Context) (identity.Principal, bool) {
	principal, ok := ctx.Value(principalKey).(identity.Principal)
	return principal, ok
}

func withDecision(ctx context.Context, decision policy.Decision) context.Context {
	return context.WithValue(ctx, decisionKey, decision)
}

// decisionOf returns the decision the router made for this request. Handlers
// read it to learn the caller's role and which versions they may see; they
// never decide access themselves.
func decisionOf(ctx context.Context) policy.Decision {
	decision, ok := ctx.Value(decisionKey).(policy.Decision)
	if !ok {
		// Reaching a handler without a decision is impossible through the
		// router; returning the empty decision keeps a mistake closed rather
		// than open.
		return policy.Decision{}
	}
	return decision
}
