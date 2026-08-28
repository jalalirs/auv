package httpapi

import (
	"log/slog"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/config"
)

// NewServer applies the repository's bounded HTTP behavior.
func NewServer(config config.Config, handler http.Handler, logger *slog.Logger) *http.Server {
	return &http.Server{
		Addr:              config.Address,
		Handler:           handler,
		ReadHeaderTimeout: config.ReadHeaderTimeout,
		ReadTimeout:       config.ReadTimeout,
		WriteTimeout:      config.WriteTimeout,
		IdleTimeout:       config.IdleTimeout,
		ErrorLog:          slog.NewLogLogger(logger.Handler(), slog.LevelError),
	}
}
