package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/compute"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// listQueues lists the queues the caller may submit to.
//
// Every queue reports how many devices it holds and how many are free, because
// "one free of two" is the only thing anyone actually wants to know about a
// queue, and making each caller work it out would mean each caller working it
// out slightly differently.
func (d *Dependencies) listQueues(w http.ResponseWriter, r *http.Request) {
	subject, _ := subjectOf(r.Context())
	decided, err := d.Authorizer.Assets(r.Context(), subject, policy.ScopeQueue)
	if err != nil {
		writeError(w, r, err)
		return
	}
	queues, err := d.Compute.Queues(r.Context(), decided.All, decided.BoundIDs)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"queues": queues})
}

type createQueueRequest struct {
	Slug         string `json:"slug"`
	Name         string `json:"name"`
	Summary      string `json:"summary"`
	LeaseSeconds int    `json:"leaseSeconds"`
}

// createQueue opens a queue.
func (d *Dependencies) createQueue(w http.ResponseWriter, r *http.Request) {
	var request createQueueRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	var created compute.Queue
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Compute.CreateQueue(r.Context(), conn, compute.QueueSpec{
			Slug:         request.Slug,
			Name:         request.Name,
			Summary:      request.Summary,
			LeaseSeconds: request.LeaseSeconds,
			CreatedBy:    principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.QueueOpen),
			SubjectKind: "queue", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": created.Slug, "leaseSeconds": created.LeaseSeconds},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// readQueue reads one queue.
func (d *Dependencies) readQueue(w http.ResponseWriter, r *http.Request) {
	queue, err := d.Compute.Queue(r.Context(), r.PathValue("queueId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, queue)
}

type addDeviceRequest struct {
	TargetID    string `json:"targetId"`
	DeviceIndex int    `json:"deviceIndex"`
	UUID        string `json:"uuid"`
	Model       string `json:"model"`
	MemoryBytes int64  `json:"memoryBytes"`
}

// addDevice places a device in a queue.
//
// Idempotent on the device's UUID, because an agent re-registers what it found
// every time it starts and a restarted host must not appear to have doubled its
// own capacity.
func (d *Dependencies) addDevice(w http.ResponseWriter, r *http.Request) {
	var request addDeviceRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	queueID := r.PathValue("queueId")

	var device compute.Device
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		device, err = d.Compute.AddDevice(r.Context(), conn, compute.DeviceSpec{
			QueueID:     queueID,
			TargetID:    request.TargetID,
			DeviceIndex: request.DeviceIndex,
			UUID:        request.UUID,
			Model:       request.Model,
			MemoryBytes: request.MemoryBytes,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.QueueOpen),
			SubjectKind: "queue", SubjectID: queueID, Outcome: audit.Succeeded,
			Detail: map[string]any{"device": device.UUID, "model": device.Model},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, device)
}

// listDevices lists the devices in a queue.
func (d *Dependencies) listDevices(w http.ResponseWriter, r *http.Request) {
	devices, err := d.Compute.Devices(r.Context(), r.PathValue("queueId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"devices": devices})
}

// grantQueue grants the use of a queue.
func (d *Dependencies) grantQueue(w http.ResponseWriter, r *http.Request) {
	d.grantAsset(w, r, policy.ScopeQueue, policy.QueueGrant, "queue", r.PathValue("queueId"))
}

// readQueueGrants lists who may submit to a queue.
func (d *Dependencies) readQueueGrants(w http.ResponseWriter, r *http.Request) {
	bindings, err := d.Authorizer.BindingsAtScope(r.Context(), policy.ScopeQueue,
		r.PathValue("queueId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"grants": bindings})
}
