// Package reqctx carries the few facts that belong to a request rather than to
// a component: which request it is, and who is making it.
//
// Both are set once by middleware and read everywhere. Keeping them in one
// package means there is one answer to "who is acting", which the audit record
// and the decision point both depend on.
package reqctx

import "context"

type contextKey int

const (
	requestIDKey contextKey = iota
	subjectKey
)

// WithRequestID attaches the identifier that ties together every record
// written while serving one request: audit events, denials, admissions, and
// refusals.
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, requestIDKey, id)
}

// RequestID returns the request identifier, or "unattributed" when called
// outside a request, such as from a background reaper.
func RequestID(ctx context.Context) string {
	if id, ok := ctx.Value(requestIDKey).(string); ok && id != "" {
		return id
	}
	return "unattributed"
}

// WithSubject attaches the authenticated actor.
func WithSubject(ctx context.Context, subject any) context.Context {
	return context.WithValue(ctx, subjectKey, subject)
}

// RawSubject returns the attached actor, if any. The http layer wraps this in
// a typed accessor; nothing else reads it directly.
func RawSubject(ctx context.Context) (any, bool) {
	subject := ctx.Value(subjectKey)
	return subject, subject != nil
}
