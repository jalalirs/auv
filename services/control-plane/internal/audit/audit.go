// Package audit keeps the append-only record of what was done.
//
// Every mutation writes exactly one event, in the same transaction as the
// change it describes, so the record and the change succeed or fail together.
// The table refuses updates and deletes, so history cannot be tidied.
package audit

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
)

// Outcome states whether the action described succeeded.
type Outcome string

const (
	Succeeded Outcome = "succeeded"
	Failed    Outcome = "failed"
)

// Event is one recorded action.
type Event struct {
	ActorID     string
	Action      string
	SubjectKind string
	SubjectID   string
	Outcome     Outcome
	// Detail carries what a reader would need to understand the change without
	// reconstructing it. It never carries secrets.
	Detail map[string]any
}

// Recorder writes the audit record.
type Recorder struct{}

// NewRecorder builds the audit recorder.
func NewRecorder() *Recorder { return &Recorder{} }

// Record writes one event on the connection performing the change, so that a
// rolled-back change leaves no claim that it happened.
func (r *Recorder) Record(ctx context.Context, conn db.Conn, event Event) error {
	if event.Action == "" || event.SubjectKind == "" {
		return fmt.Errorf("an audit event names its action and its subject")
	}
	detail := event.Detail
	if detail == nil {
		detail = map[string]any{}
	}
	encoded, err := json.Marshal(detail)
	if err != nil {
		return fmt.Errorf("encoding audit detail: %w", err)
	}

	var actorID, subjectID *string
	if event.ActorID != "" {
		actorID = &event.ActorID
	}
	if event.SubjectID != "" {
		subjectID = &event.SubjectID
	}
	outcome := event.Outcome
	if outcome == "" {
		outcome = Succeeded
	}

	_, err = conn.Exec(ctx, `
		INSERT INTO audit.event
		    (id, actor_id, action, subject_kind, subject_id, outcome, request_id, detail)
		VALUES ($1, $2, $3, $4, $5, $6::audit.outcome, $7, $8)`,
		ids.New(ids.KindAuditEvent), actorID, event.Action, event.SubjectKind,
		subjectID, string(outcome), reqctx.RequestID(ctx), encoded)
	if err != nil {
		return fmt.Errorf("recording an audit event: %w", err)
	}
	return nil
}
