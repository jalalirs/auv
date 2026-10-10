package httpapi

import (
	"errors"
	"net/http"
	"strconv"
	"time"

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
		OrgID:     r.PathValue("orgId"),
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

// A part can take a while on a poor connection; the server's ordinary read
// deadline is for requests that carry a few kilobytes of JSON.
const partTakes = 10 * time.Minute

// putUploadPart takes one part of an upload through the API, for a caller
// that cannot reach the store directly or wants to resume after a drop.
func (d *Dependencies) putUploadPart(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	number, err := strconv.Atoi(r.PathValue("number"))
	if err != nil {
		writeError(w, r, errors.Join(domain.ErrInvalid, err))
		return
	}
	if r.ContentLength <= 0 {
		writeError(w, r, errors.Join(domain.ErrInvalid, errors.New("a part states its length")))
		return
	}
	control := http.NewResponseController(w)
	_ = control.SetReadDeadline(time.Now().Add(partTakes))
	_ = control.SetWriteDeadline(time.Now().Add(partTakes + time.Minute))

	if err := d.Objects.PutPart(r.Context(), principal.ID, r.PathValue("orgId"), r.PathValue("grantId"),
		number, r.Body, r.ContentLength); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"number": number, "sizeBytes": r.ContentLength})
}

// uploadProgress says which parts of an upload have arrived.
func (d *Dependencies) uploadProgress(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	progress, err := d.Objects.Progress(r.Context(), principal.ID, r.PathValue("orgId"), r.PathValue("grantId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, progress)
}

// storageOf says what an organisation holds against what it may.
func (d *Dependencies) storageOf(w http.ResponseWriter, r *http.Request) {
	usage, err := d.Objects.Usage(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, usage)
}

// heldObjects lists what an organisation holds, newest first.
func (d *Dependencies) heldObjects(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	held, err := d.Objects.Holdings(r.Context(), r.PathValue("orgId"), limit)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"objects": held})
}

// releaseObject lets an organisation go of an object. The bytes go too when
// nobody else holds them and nothing is made of them.
func (d *Dependencies) releaseObject(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	orgID, objectID := r.PathValue("orgId"), r.PathValue("objectId")
	released, err := d.Objects.Release(r.Context(), orgID, objectID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.ObjectRelease),
			SubjectKind: "object", SubjectID: objectID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "collected": released.Collected,
				"keptBecause": released.KeptBecause, "freedBytes": released.FreedBytes},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, released)
}

type limitRequest struct {
	LimitBytes int64 `json:"limitBytes"`
}

// setStorageLimit sets what an organisation may hold. The platform decides
// it, because the disks are the platform's.
func (d *Dependencies) setStorageLimit(w http.ResponseWriter, r *http.Request) {
	var request limitRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")
	if err := d.Objects.SetLimit(r.Context(), principal.ID, orgID, request.LimitBytes); err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "organisation", SubjectID: orgID, Outcome: audit.Succeeded,
			Detail: map[string]any{"storageLimitBytes": request.LimitBytes},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	usage, err := d.Objects.Usage(r.Context(), orgID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, usage)
}
