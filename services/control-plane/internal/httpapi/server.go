package httpapi

import (
	"context"
	"log/slog"
	"net"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/config"
)

// NewServer builds the HTTP server with the timeouts a public listener needs:
// a slow client must not be able to hold a connection open indefinitely.
func NewServer(settings config.Config, handler http.Handler, logger *slog.Logger) *http.Server {
	return &http.Server{
		Addr:              settings.Address,
		Handler:           handler,
		ReadHeaderTimeout: settings.ReadHeaderTimeout,
		ReadTimeout:       settings.ReadTimeout,
		WriteTimeout:      settings.WriteTimeout,
		IdleTimeout:       settings.IdleTimeout,
		ErrorLog:          slog.NewLogLogger(logger.Handler(), slog.LevelWarn),
		BaseContext:       func(net.Listener) context.Context { return context.Background() },
	}
}
