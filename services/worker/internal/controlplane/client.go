// Package controlplane is the worker's half of the lease protocol.
//
// A worker holds authority over the work queue and over nothing else. Every
// call here is authorised either by that authority or by the lease token the
// worker was given when it took the work, so a worker cannot reach anything it
// is not currently running.
package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client talks to the control plane.
type Client struct {
	baseURL    string
	credential string
	http       *http.Client
}

// New builds a client for a control plane.
func New(baseURL, credential string, timeout time.Duration) *Client {
	return &Client{
		baseURL:    strings.TrimRight(baseURL, "/"),
		credential: credential,
		http:       &http.Client{Timeout: timeout},
	}
}

// Input is one file a job reads.
type Input struct {
	Name         string `json:"name"`
	RelativePath string `json:"relativePath"`
	ObjectID     string `json:"objectId"`
	SHA256       string `json:"sha256"`
	MediaType    string `json:"mediaType"`
	SizeBytes    int64  `json:"sizeBytes"`
}

// Output is one file a job is expected to produce.
type Output struct {
	Name         string `json:"name"`
	RelativePath string `json:"relativePath"`
	MediaType    string `json:"mediaType"`
	MaxSizeBytes int64  `json:"maxSizeBytes"`
}

// Job is the work itself.
type Job struct {
	ID                 string   `json:"id"`
	OrgID              string   `json:"orgId"`
	RecipeID           string   `json:"recipeId"`
	ImageDigest        string   `json:"imageDigest"`
	Command            []string `json:"command"`
	Args               []string `json:"args"`
	Inputs             []Input  `json:"inputs"`
	Outputs            []Output `json:"outputs"`
	RequestCPU         float64  `json:"requestCpu"`
	RequestMemoryBytes int64    `json:"requestMemoryBytes"`
	RequestGPU         int      `json:"requestGpu"`
	WalltimeSeconds    int      `json:"walltimeSeconds"`
	// Egress is "none" for every job an institution submits, and "internet"
	// only for work the platform admitted with that capability.
	Egress string `json:"egress"`
}

// Lease is work handed to this worker, with the token proving it holds it.
type Lease struct {
	AttemptID string    `json:"attemptId"`
	Token     string    `json:"token"`
	ExpiresAt time.Time `json:"expiresAt"`
	Job       Job       `json:"job"`
}

// Heartbeat is what a worker learns each time it reports that it is alive.
type Heartbeat struct {
	ExpiresAt time.Time `json:"expiresAt"`
	Cancelled bool      `json:"cancelled"`
}

// Grant is permission to place specific bytes in storage.
type Grant struct {
	ID        string    `json:"id"`
	UploadURL string    `json:"uploadUrl"`
	ExpiresAt time.Time `json:"expiresAt"`
}

// Take asks for one job. A nil lease means there is nothing to do.
func (c *Client) Take(ctx context.Context, targetName string) (*Lease, error) {
	var lease Lease
	status, err := c.call(ctx, http.MethodPost, "/api/v1/work/lease",
		map[string]any{"targetName": targetName}, &lease)
	if err != nil {
		return nil, err
	}
	if status == http.StatusNoContent {
		return nil, nil
	}
	return &lease, nil
}

// Beat extends the lease and reports whether the work should stop.
func (c *Client) Beat(ctx context.Context, attemptID, token string) (Heartbeat, error) {
	var beat Heartbeat
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/heartbeat",
		map[string]any{"token": token}, &beat)
	return beat, err
}

// ReportStarted records that the container is running, and where.
func (c *Client) ReportStarted(ctx context.Context, attemptID, token, placementRef string) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/started",
		map[string]any{"token": token, "placementRef": placementRef}, nil)
	return err
}

// ReportProgress adds an entry to the job's account of itself.
func (c *Client) ReportProgress(ctx context.Context, attemptID, token string, detail map[string]any) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/progress",
		map[string]any{"token": token, "detail": detail}, nil)
	return err
}

// InputURL asks where one input's bytes can be read from.
func (c *Client) InputURL(ctx context.Context, attemptID, token, name string) (Input, string, error) {
	var answer struct {
		Input   Input  `json:"input"`
		ReadURL string `json:"readUrl"`
	}
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/inputs",
		map[string]any{"token": token, "name": name}, &answer)
	return answer.Input, answer.ReadURL, err
}

// RequestUpload asks for permission to place one output in storage.
func (c *Client) RequestUpload(ctx context.Context, attemptID, token, name, sha256 string, size int64) (Grant, error) {
	var grant Grant
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/uploads",
		map[string]any{"token": token, "name": name, "sha256": sha256, "sizeBytes": size}, &grant)
	return grant, err
}

// ConfirmUpload asks the control plane to check what arrived against what was
// declared. It reports the identifier of the recorded object.
func (c *Client) ConfirmUpload(ctx context.Context, attemptID, grantID string) (string, error) {
	var object struct {
		ID string `json:"id"`
	}
	_, err := c.call(ctx, http.MethodPost,
		"/api/v1/work/"+attemptID+"/uploads/"+grantID+"/confirm", map[string]any{}, &object)
	return object.ID, err
}

// RecordOutput records one file the work produced.
func (c *Client) RecordOutput(ctx context.Context, attemptID, token, name, objectID string) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/outputs",
		map[string]any{"token": token, "name": name, "objectId": objectID}, nil)
	return err
}

// Finish reports how the attempt ended.
func (c *Client) Finish(ctx context.Context, attemptID, token, outcome string, exitCode int, failureClass string) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/work/"+attemptID+"/finish",
		map[string]any{
			"token": token, "outcome": outcome,
			"exitCode": exitCode, "failureClass": failureClass,
		}, nil)
	return err
}

// Failure is an error the control plane reported, carrying the code it used so
// that a caller can distinguish a lease it has lost from a fault.
type Failure struct {
	Status  int
	Code    string
	Message string
}

func (f *Failure) Error() string {
	return fmt.Sprintf("control plane refused: %s (%s)", f.Message, f.Code)
}

// LeaseLost reports whether the control plane has taken the work back, in
// which case the worker must stop rather than keep writing results.
func (f *Failure) LeaseLost() bool { return f.Code == "lease_invalid" }

func (c *Client) call(ctx context.Context, method, path string, body any, into any) (int, error) {
	encoded, err := json.Marshal(body)
	if err != nil {
		return 0, fmt.Errorf("encoding a request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, bytes.NewReader(encoded))
	if err != nil {
		return 0, err
	}
	request.Header.Set("Authorization", "Service "+c.credential)
	request.Header.Set("Content-Type", "application/json")

	response, err := c.http.Do(request)
	if err != nil {
		return 0, fmt.Errorf("reaching the control plane: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode >= 400 {
		var reported struct {
			Error struct {
				Code    string `json:"code"`
				Message string `json:"message"`
			} `json:"error"`
		}
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 1<<16))
		_ = json.Unmarshal(raw, &reported)
		if reported.Error.Code == "" {
			reported.Error.Code = "unknown"
			reported.Error.Message = strings.TrimSpace(string(raw))
		}
		return response.StatusCode, &Failure{
			Status: response.StatusCode, Code: reported.Error.Code, Message: reported.Error.Message,
		}
	}

	if into == nil || response.StatusCode == http.StatusNoContent {
		_, _ = io.Copy(io.Discard, response.Body)
		return response.StatusCode, nil
	}
	if err := json.NewDecoder(response.Body).Decode(into); err != nil {
		return response.StatusCode, fmt.Errorf("reading a response: %w", err)
	}
	return response.StatusCode, nil
}

// ── Dives ────────────────────────────────────────────────────────────────────

// ErrNothingToRun is what ClaimDive reports when the platform has no work.
// The ordinary case, and not a failure: an agent asks constantly and mostly
// there is nothing, and treating that as an error would fill a log with the
// platform working correctly.
var ErrNothingToRun = errors.New("nothing to run")

// ClaimDive takes the next dive this host can run.
func (c *Client) ClaimDive(ctx context.Context, targetName string, into any) error {
	status, err := c.call(ctx, http.MethodPost, "/api/v1/runs/claim",
		map[string]any{"targetId": targetName}, into)
	if err != nil {
		return err
	}
	if status == http.StatusNoContent {
		return ErrNothingToRun
	}
	return nil
}

// RunPackages asks what the packages a run needs contain, and where to fetch
// each file.
//
// Asked through the run rather than by naming a package: an agent holds
// authority over work and nothing else, and this is the one thing it needs to
// see of the catalogue.
func (c *Client) RunPackages(ctx context.Context, runID string) (city, vehicle PackageContents, err error) {
	var answer struct {
		City    PackageContents `json:"city"`
		Vehicle PackageContents `json:"vehicle"`
	}
	if _, err := c.call(ctx, http.MethodGet,
		"/api/v1/runs/"+runID+"/packages", nil, &answer); err != nil {
		return PackageContents{}, PackageContents{}, err
	}
	return answer.City, answer.Vehicle, nil
}

// PackageContents is one package and the files in it.
type PackageContents struct {
	VersionID string        `json:"versionId"`
	Files     []PackageFile `json:"files"`
}

// PackageFile is one file in a package, and where its bytes are.
type PackageFile struct {
	Path      string `json:"path"`
	Digest    string `json:"digest"`
	SizeBytes int64  `json:"sizeBytes"`
	MediaType string `json:"mediaType"`
	URL       string `json:"url"`
}

// DiveStarted records that the simulator is up.
func (c *Client) DiveStarted(ctx context.Context, runID string) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/runs/"+runID+"/started", nil, nil)
	return err
}

// RenewDive extends the lease on a dive still under way.
func (c *Client) RenewDive(ctx context.Context, runID string) error {
	_, err := c.call(ctx, http.MethodPost, "/api/v1/runs/"+runID+"/renew", nil, nil)
	return err
}

// RecordDiveEvent appends to what happened during a dive.
func (c *Client) RecordDiveEvent(ctx context.Context, runID, kind string,
	simulated *float64, detail any) error {
	body := map[string]any{"kind": kind}
	if simulated != nil {
		body["simulatedSeconds"] = *simulated
	}
	if detail != nil {
		body["detail"] = detail
	}
	_, err := c.call(ctx, http.MethodPost, "/api/v1/runs/"+runID+"/events", body, nil)
	return err
}

// FinishDive says how a dive ended, and is the last thing anything says about
// it: the record refuses to rewrite a finished run.
func (c *Client) FinishDive(ctx context.Context, runID, state string,
	outcome any, failure string) error {
	body := map[string]any{"state": state}
	if outcome != nil {
		body["outcome"] = outcome
	}
	if failure != "" {
		body["failureReason"] = failure
	}
	_, err := c.call(ctx, http.MethodPost, "/api/v1/runs/"+runID+"/finished", body, nil)
	return err
}
