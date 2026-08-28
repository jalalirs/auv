package httpapi

import (
	"context"
	"net/http"
	"time"
)

// contextWithTimeout bounds one piece of work within a request, so that a slow
// dependency cannot hold a connection open indefinitely.
func contextWithTimeout(r *http.Request, limit time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(r.Context(), limit)
}
