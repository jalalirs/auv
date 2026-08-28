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
type Grant struct {
	ID        string        `json:"id"`
	Bucket    domain.Bucket `json:"bucket"`
	UploadURL string        `json:"uploadUrl"`
	ExpiresAt time.Time     `json:"expiresAt"`
}

// Objects records what is stored. It is the only component that writes the
// object registry, so every recorded object has had its digest verified.
type Objects struct {
	pool           *db.Pool
	blobs          *Blobs
	grantLifetime  time.Duration
	maxObjectBytes int64
}

// NewObjects builds the object registry over a byte store.
func NewObjects(pool *db.Pool, blobs *Blobs, grantLifetime time.Duration, maxObjectBytes int64) *Objects {
	return &Objects{
		pool:           pool,
		blobs:          blobs,
		grantLifetime:  grantLifetime,
		maxObjectBytes: maxObjectBytes,
	}
}

// UploadRequest is a caller's claim about bytes it intends to upload.
type UploadRequest struct {
	Bucket    domain.Bucket
	Digest    domain.Digest
	SizeBytes int64
	MediaType string
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

	grant := Grant{
		ID:        ids.New(ids.KindUploadGrant),
		Bucket:    request.Bucket,
		ExpiresAt: time.Now().Add(o.grantLifetime),
	}
	_, err := o.pool.Exec(ctx, `
		INSERT INTO store.upload_grant
		    (id, bucket, declared_sha256, declared_size, declared_media, issued_to, expires_at)
		VALUES ($1, $2::store.bucket, $3, $4, $5, $6, $7)`,
		grant.ID, string(request.Bucket), request.Digest.Bytes(),
		request.SizeBytes, request.MediaType, principalID, grant.ExpiresAt)
	if err != nil {
		return Grant{}, fmt.Errorf("recording an upload grant: %w", err)
	}

	uploadURL, err := o.blobs.PresignPut(ctx, request.Bucket, grant.ID, audience)
	if err != nil {
		return Grant{}, err
	}
	grant.UploadURL = uploadURL
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
	)
	err := o.pool.QueryRow(ctx, `
		SELECT bucket, declared_sha256, declared_size, declared_media, issued_to, expires_at, confirmed_at
		FROM store.upload_grant WHERE id = $1`, grantID).
		Scan(&bucket, &declaredRaw, &declaredSize, &declaredMedia, &issuedTo, &expiresAt, &confirmedAt)
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
