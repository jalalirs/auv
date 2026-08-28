package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

type uploadRequest struct {
	Bucket    string `json:"bucket"`
	SHA256    string `json:"sha256"`
	SizeBytes int64  `json:"sizeBytes"`
	MediaType string `json:"mediaType"`
}

// requestUpload issues a short-lived grant to place specific bytes in storage.
//
// What the caller claims about those bytes is written down now, so that it can
// be checked against what actually arrives.
func (d *Dependencies) requestUpload(w http.ResponseWriter, r *http.Request) {
	var request uploadRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	bucket, err := domain.ParseBucket(request.Bucket)
	if err != nil {
		writeError(w, r, err)
		return
	}
	digest, err := domain.ParseDigest(request.SHA256)
	if err != nil {
		writeError(w, r, err)
		return
	}

	grant, err := d.Objects.RequestUpload(r.Context(), principal.ID, storage.UploadRequest{
		Bucket:    bucket,
		Digest:    digest,
		SizeBytes: request.SizeBytes,
		MediaType: request.MediaType,
	}, storage.External)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, grant)
}

// confirmUpload checks what actually arrived against what was declared.
//
// Bytes that are not what they said they were are discarded and nothing is
// recorded, so no object in the registry has an unverified digest.
func (d *Dependencies) confirmUpload(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	grantID := r.PathValue("grantId")

	object, err := d.Objects.ConfirmUpload(r.Context(), principal.ID, grantID)
	if err != nil {
		// A rejected upload is worth recording: it is how tampering or a broken
		// client shows up later.
		if recordErr := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			return d.Audit.Record(r.Context(), conn, audit.Event{
				ActorID: principal.ID, Action: string(policy.ObjectUpload),
				SubjectKind: "upload_grant", SubjectID: grantID, Outcome: audit.Failed,
				Detail: map[string]any{"reason": err.Error()},
			})
		}); recordErr != nil {
			d.Logger.ErrorContext(r.Context(), "could not record a rejected upload",
				"error", recordErr)
		}
		writeError(w, r, err)
		return
	}

	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.ObjectUpload),
			SubjectKind: "object", SubjectID: object.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"bucket": string(object.Bucket), "sha256": object.SHA256,
				"sizeBytes": object.SizeBytes,
			},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, object)
}
