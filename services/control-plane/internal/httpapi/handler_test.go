package httpapi

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/platform"
)

func TestEndpoints(t *testing.T) {
	handler := NewHandler(
		platform.Build("1.2.3", "abc123", "2026-08-28T12:00:00Z"),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
	)

	tests := []struct {
		path       string
		wantStatus string
	}{
		{"/health/live", "live"},
		{"/health/ready", "ready"},
	}

	for _, test := range tests {
		t.Run(test.path, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, test.path, nil)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)

			if response.Code != http.StatusOK {
				t.Fatalf("status = %d, want 200", response.Code)
			}
			if response.Header().Get(requestIDHeader) == "" {
				t.Fatal("X-Request-ID is empty")
			}

			var body statusResponse
			if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if body.Status != test.wantStatus {
				t.Fatalf("status body = %q, want %q", body.Status, test.wantStatus)
			}
		})
	}
}

func TestPlatformContract(t *testing.T) {
	handler := NewHandler(
		platform.Build("1.2.3", "abc123", "2026-08-28T12:00:00Z"),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
	)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/platform", nil)
	request.Header.Set(requestIDHeader, "test-request")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", response.Code)
	}
	if response.Header().Get(requestIDHeader) != "test-request" {
		t.Fatalf("X-Request-ID = %q", response.Header().Get(requestIDHeader))
	}

	var body platform.Info
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Name != "Coral City" || body.Service != "control-plane" || body.Version != "1.2.3" {
		t.Fatalf("unexpected platform response: %+v", body)
	}
}

func TestUnknownRoute(t *testing.T) {
	handler := NewHandler(
		platform.Build("", "", ""),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/missing", nil))

	if response.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", response.Code)
	}
}
