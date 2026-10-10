package storage

import (
	"context"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// ErrDigestMismatch reports bytes that are not what the uploader said they
// were. The bytes are discarded and no object is recorded.
var ErrDigestMismatch = errors.New("the uploaded bytes are not what was declared")

// ErrGrantSpent reports an upload grant that has already been confirmed or has
// expired.
var ErrGrantSpent = errors.New("that upload grant can no longer be used")

// Object is the record of stored bytes.
type Object struct {
	ID         string        `json:"id"`
	Bucket     domain.Bucket `json:"bucket"`
	Digest     domain.Digest `json:"-"`
	SHA256     string        `json:"sha256"`
	SizeBytes  int64         `json:"sizeBytes"`
	MediaType  string        `json:"mediaType"`
	UploadedBy string        `json:"uploadedBy"`
	UploadedAt time.Time     `json:"uploadedAt"`
}

// Grant is permission to place specific bytes in storage, valid briefly.
//
// Bytes reach the store one of two ways: straight to it at UploadURL, which
// only a caller on the platform's network can reach, or through the API in
// parts (PUT …/uploads/{grant}/parts/{n}), which works wherever the API does
// and resumes after a drop. Parts says how many and how large; a small upload
// is one part.
type Grant struct {
	ID        string        `json:"id"`
	Bucket    domain.Bucket `json:"bucket"`
	UploadURL string        `json:"uploadUrl,omitempty"`
	Parts     PartPlan      `json:"parts"`
	ExpiresAt time.Time     `json:"expiresAt"`
}

// Objects records what is stored. It is the only component that writes the
// object registry, so every recorded object has had its digest verified.
type Objects struct {
	pool           *db.Pool
	blobs          *Blobs
	grantLifetime  time.Duration
	maxObjectBytes int64
	// Uploads larger than one part arrive in parts, and live long enough to
	// be resumed. An organisation with no limit of its own may hold
	// defaultLimit bytes.
	partBytes     int64
	partsLifetime time.Duration
	defaultLimit  int64
}

// NewObjects builds the object registry over a byte store.
func NewObjects(pool *db.Pool, blobs *Blobs, grantLifetime time.Duration, maxObjectBytes int64) *Objects {
	return &Objects{
		pool:           pool,
		blobs:          blobs,
		grantLifetime:  grantLifetime,
		maxObjectBytes: maxObjectBytes,
		partBytes:      DefaultPartBytes,
		partsLifetime:  DefaultPartsLifetime,
		defaultLimit:   DefaultOrgLimitBytes,
	}
}

// WithLimits sets how large a part is, how long a multipart upload may take,
// and what an organisation may hold when nobody set its limit.
func (o *Objects) WithLimits(partBytes int64, partsLifetime time.Duration, defaultLimit int64) *Objects {
	if partBytes > 0 {
		o.partBytes = partBytes
	}
	if partsLifetime > 0 {
		o.partsLifetime = partsLifetime
	}
	if defaultLimit > 0 {
		o.defaultLimit = defaultLimit
	}
	return o
}

// UploadRequest is a caller's claim about bytes it intends to upload.
type UploadRequest struct {
	Bucket    domain.Bucket
	Digest    domain.Digest
	SizeBytes int64
	MediaType string
	// OrgID is the organisation the bytes are for: it will hold them, and
	// they count against its limit. Empty for the platform's own work (a
	// run's recording, a job's output).
	OrgID string
}

// RequestUpload issues a short-lived grant to upload specific bytes.
//
// The claim recorded here is what the bytes are checked against on
// confirmation, which is why it is written down rather than kept by the client.
func (o *Objects) RequestUpload(ctx context.Context, principalID string, request UploadRequest, audience Audience) (Grant, error) {
	if request.SizeBytes <= 0 {
		return Grant{}, fmt.Errorf("%w: an object has content", domain.ErrInvalid)
	}
	if request.SizeBytes > o.maxObjectBytes {
		return Grant{}, fmt.Errorf("%w: %d bytes exceeds the %d byte limit for a single object",
			domain.ErrInvalid, request.SizeBytes, o.maxObjectBytes)
	}
	if request.MediaType == "" {
		return Grant{}, fmt.Errorf("%w: an object states its media type", domain.ErrInvalid)
	}

	if request.OrgID != "" {
		if err := o.roomFor(ctx, request.OrgID, request.Bucket, request.Digest, request.SizeBytes); err != nil {
			return Grant{}, err
		}
	}

	// The platform's own work (a worker inside the network) puts its bytes
	// straight into the store in one piece; an organisation's upload of more
	// than a part arrives in parts, through the API, from anywhere.
	plan := PartPlan{Count: 1, PartBytes: request.SizeBytes}
	if request.OrgID != "" {
		plan = planParts(request.SizeBytes, o.partBytes)
	}
	grant := Grant{
		ID:        ids.New(ids.KindUploadGrant),
		Bucket:    request.Bucket,
		Parts:     plan,
		ExpiresAt: time.Now().Add(o.grantLifetime),
	}
	var multipartID *string
	var partBytes *int64
	if plan.Count > 1 {
		id, err := o.blobs.StartParts(ctx, request.Bucket, grant.ID)
		if err != nil {
			return Grant{}, err
		}
		multipartID, partBytes = &id, &plan.PartBytes
		grant.ExpiresAt = time.Now().Add(o.partsLifetime)
	}
	var orgID *string
	if request.OrgID != "" {
		orgID = &request.OrgID
	}
	_, err := o.pool.Exec(ctx, `
		INSERT INTO store.upload_grant
		    (id, bucket, declared_sha256, declared_size, declared_media, issued_to, expires_at,
		     org_id, multipart_id, part_bytes)
		VALUES ($1, $2::store.bucket, $3, $4, $5, $6, $7, $8, $9, $10)`,
		grant.ID, string(request.Bucket), request.Digest.Bytes(),
		request.SizeBytes, request.MediaType, principalID, grant.ExpiresAt,
		orgID, multipartID, partBytes)
	if err != nil {
		return Grant{}, fmt.Errorf("recording an upload grant: %w", err)
	}

	if plan.Count == 1 {
		uploadURL, err := o.blobs.PresignPut(ctx, request.Bucket, grant.ID, audience)
		if err != nil {
			return Grant{}, err
		}
		grant.UploadURL = uploadURL
	}
	return grant, nil
}

// ConfirmUpload verifies what actually arrived against what was declared.
//
// Bytes that do not match their declaration are discarded and no object is
// recorded, so nothing in the registry has an unverified digest.
func (o *Objects) ConfirmUpload(ctx context.Context, principalID, grantID string) (Object, error) {
	var (
		bucket        domain.Bucket
		declaredRaw   []byte
		declaredSize  int64
		declaredMedia string
		issuedTo      string
		expiresAt     time.Time
		confirmedAt   *time.Time
		orgID         *string
		multipartID   *string
		partBytes     *int64
	)
	err := o.pool.QueryRow(ctx, `
		SELECT bucket, declared_sha256, declared_size, declared_media, issued_to, expires_at, confirmed_at,
		       org_id, multipart_id, part_bytes
		FROM store.upload_grant WHERE id = $1`, grantID).
		Scan(&bucket, &declaredRaw, &declaredSize, &declaredMedia, &issuedTo, &expiresAt, &confirmedAt,
			&orgID, &multipartID, &partBytes)
	if err != nil {
		return Object{}, db.Translate(err)
	}
	if issuedTo != principalID {
		// The grant belongs to someone else; reporting absence avoids
		// confirming that it exists.
		return Object{}, db.ErrNotFound
	}
	if confirmedAt != nil || time.Now().After(expiresAt) {
		return Object{}, ErrGrantSpent
	}

	declared, err := domain.DigestFromBytes(declaredRaw)
	if err != nil {
		return Object{}, err
	}

	if multipartID != nil {
		parts, err := o.blobs.Parts(ctx, bucket, grantID, *multipartID)
		if err != nil {
			return Object{}, err
		}
		plan := PartPlan{Count: partCount(declaredSize, *partBytes), PartBytes: *partBytes}
		if gaps := missingParts(parts, plan, declaredSize); len(gaps) > 0 {
			return Object{}, &PartsMissing{Missing: gaps, Of: plan.Count}
		}
		if err := o.blobs.FinishParts(ctx, bucket, grantID, *multipartID, parts); err != nil {
			return Object{}, err
		}
	}

	actual, size, err := o.blobs.VerifyStaged(ctx, bucket, grantID)
	if err != nil {
		return Object{}, err
	}
	if actual != declared || size != declaredSize {
		if discardErr := o.blobs.DiscardStaged(ctx, bucket, grantID); discardErr != nil {
			return Object{}, fmt.Errorf("%w (and the bytes could not be discarded: %v)",
				ErrDigestMismatch, discardErr)
		}
		return Object{}, fmt.Errorf("%w: declared %s at %d bytes, received %s at %d bytes",
			ErrDigestMismatch, declared, declaredSize, actual, size)
	}

	if err := o.blobs.PromoteStaged(ctx, bucket, grantID, actual); err != nil {
		return Object{}, err
	}

	object := Object{
		ID:         ids.New(ids.KindObject),
		Bucket:     bucket,
		Digest:     actual,
		SHA256:     actual.String(),
		SizeBytes:  size,
		MediaType:  declaredMedia,
		UploadedBy: principalID,
	}
	err = o.pool.InTransaction(ctx, func(conn db.Conn) error {
		// Identical bytes in the same bucket are one object however many times
		// they arrive; the earlier record wins and keeps its provenance.
		err := conn.QueryRow(ctx, `
			INSERT INTO store.object (id, bucket, sha256, size_bytes, media_type, uploaded_by)
			VALUES ($1, $2::store.bucket, $3, $4, $5, $6)
			ON CONFLICT (bucket, sha256) DO NOTHING
			RETURNING id, uploaded_at`,
			object.ID, string(bucket), actual.Bytes(), size, declaredMedia, principalID).
			Scan(&object.ID, &object.UploadedAt)
		if errors.Is(db.Translate(err), db.ErrNotFound) {
			err = conn.QueryRow(ctx, `
				SELECT id, media_type, uploaded_by, uploaded_at
				FROM store.object WHERE bucket = $1::store.bucket AND sha256 = $2`,
				string(bucket), actual.Bytes()).
				Scan(&object.ID, &object.MediaType, &object.UploadedBy, &object.UploadedAt)
		}
		if err != nil {
			return fmt.Errorf("recording an object: %w", err)
		}

		_, err = conn.Exec(ctx,
			`UPDATE store.upload_grant SET confirmed_at = now(), object_id = $2 WHERE id = $1`,
			grantID, object.ID)
		if err != nil || orgID == nil {
			return err
		}
		// Held by the organisation it was uploaded for. The same bytes already
		// held stay held once.
		_, err = conn.Exec(ctx, `
			INSERT INTO store.holding (org_id, object_id, held_by) VALUES ($1, $2, $3)
			ON CONFLICT DO NOTHING`, *orgID, object.ID, principalID)
		return err
	})
	if err != nil {
		return Object{}, err
	}
	return object, nil
}

// Object reads one object record.
func (o *Objects) Object(ctx context.Context, id string) (Object, error) {
	var object Object
	var raw []byte
	err := o.pool.QueryRow(ctx, `
		SELECT id, bucket, sha256, size_bytes, media_type, uploaded_by, uploaded_at
		FROM store.object WHERE id = $1`, id).
		Scan(&object.ID, &object.Bucket, &raw, &object.SizeBytes,
			&object.MediaType, &object.UploadedBy, &object.UploadedAt)
	if err != nil {
		return Object{}, db.Translate(err)
	}
	object.Digest, err = domain.DigestFromBytes(raw)
	if err != nil {
		return Object{}, err
	}
	object.SHA256 = object.Digest.String()
	return object, nil
}

// ByDigest reads the object holding specific bytes, if it is recorded.
func (o *Objects) ByDigest(ctx context.Context, bucket domain.Bucket, digest domain.Digest) (Object, error) {
	var object Object
	var raw []byte
	err := o.pool.QueryRow(ctx, `
		SELECT id, bucket, sha256, size_bytes, media_type, uploaded_by, uploaded_at
		FROM store.object WHERE bucket = $1::store.bucket AND sha256 = $2`,
		string(bucket), digest.Bytes()).
		Scan(&object.ID, &object.Bucket, &raw, &object.SizeBytes,
			&object.MediaType, &object.UploadedBy, &object.UploadedAt)
	if err != nil {
		return Object{}, db.Translate(err)
	}
	object.Digest, err = domain.DigestFromBytes(raw)
	if err != nil {
		return Object{}, err
	}
	object.SHA256 = object.Digest.String()
	return object, nil
}

// Open reads a recorded object's bytes.
func (o *Objects) Open(ctx context.Context, object Object) (io.ReadCloser, error) {
	return o.blobs.Open(ctx, object.Bucket, object.Digest)
}

// ReadURL issues a short-lived URL to read an object's bytes, addressed to
// whichever side of the network the caller is on.
func (o *Objects) ReadURL(ctx context.Context, object Object, filename string, audience Audience) (string, error) {
	return o.blobs.PresignGet(ctx, object.Bucket, object.Digest, filename, audience)
}
