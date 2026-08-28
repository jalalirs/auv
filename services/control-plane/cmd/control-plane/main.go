package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/jalalirs/auv/services/control-plane/internal/config"
	"github.com/jalalirs/auv/services/control-plane/internal/httpapi"
	"github.com/jalalirs/auv/services/control-plane/internal/platform"
)

var (
	version = "development"
	commit  = "unknown"
	builtAt = "unknown"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(logger); err != nil {
		logger.Error("control plane stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	settings, err := config.Load()
	if err != nil {
		return err
	}

	info := platform.Build(version, commit, builtAt)
	server := httpapi.NewServer(settings, httpapi.NewHandler(info, logger), logger)
	serverErrors := make(chan error, 1)

	go func() {
		logger.Info("control plane listening",
			"address", settings.Address,
			"version", info.Version,
			"commit", info.Commit,
		)
		serverErrors <- server.ListenAndServe()
	}()

	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(signals)

	select {
	case received := <-signals:
		logger.Info("shutdown requested", "signal", received.String())
		shutdownContext, cancel := context.WithTimeout(context.Background(), settings.ShutdownTimeout)
		defer cancel()
		return server.Shutdown(shutdownContext)
	case err := <-serverErrors:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}
