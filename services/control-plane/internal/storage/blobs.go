// Package storage owns stored bytes and the record of what is stored.
//
// The object store holds bytes; the database holds their meaning. An object is
// addressed by the digest of its content, so identity survives migration from
// one store to another. The server verifies every digest itself: a client is
// never trusted to describe what it uploaded.
package storage

import (
	"context"
	"crypto/sha256"
	"fmt"
	"io"
	"net/url"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// Settings describe how to reach the object store.
type Settings struct {
	// Endpoint is where this process reaches the store.
	Endpoint string
	// PublicEndpoint is where a client reaches it. The two differ whenever the
	// service and its callers are on different networks — a container network
	// and a browser, for instance. A presigned URL is signed over its host, so
	// one signed for the wrong host is refused when it is used.
	//
	// Empty means the store is reached the same way from both sides.
	PublicEndpoint  string
	AccessKey       string
	SecretKey       string
	UseTLS          bool
	PublicUseTLS    bool
	Region          string
	BucketPrefix    string
	PresignLifetime time.Duration
}

// Audience says which side of the network a URL is being signed for.
//
// A presigned URL is signed over its host, so the same object has two correct
// URLs: one naming the address a browser or a developer's machine can reach,
// and one naming the address a component inside the platform's own network
// can. Signing the wrong one produces a URL that is refused when it is used, or
// a host that cannot be resolved at all.
type Audience int

const (
	// External is a client outside the platform's network: a browser, a
	// developer's machine, a partner institution.
	External Audience = iota
	// Internal is a component inside it, such as a worker.
	Internal
)

// Blobs is the byte store. It knows nothing about layers, cities, or people.
type Blobs struct {
	// client performs this process's own reads and writes.
	client *minio.Client
	// signer issues URLs for clients outside the platform's network. It
	// differs from client only in the host it signs for.
	signer          *minio.Client
	prefix          string
	region          string
	presignLifetime time.Duration
}

// OpenBlobs connects to the object store.
func OpenBlobs(settings Settings) (*Blobs, error) {
	client, err := minio.New(settings.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(settings.AccessKey, settings.SecretKey, ""),
		Secure: settings.UseTLS,
		Region: settings.Region,
	})
	if err != nil {
		return nil, fmt.Errorf("reaching the object store: %w", err)
	}

	signer := client
	if settings.PublicEndpoint != "" && settings.PublicEndpoint != settings.Endpoint {
		signer, err = minio.New(settings.PublicEndpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(settings.AccessKey, settings.SecretKey, ""),
			Secure: settings.PublicUseTLS,
			Region: settings.Region,
		})
		if err != nil {
			return nil, fmt.Errorf("preparing to sign URLs for %s: %w", settings.PublicEndpoint, err)
		}
	}

	return &Blobs{
		client:          client,
		signer:          signer,
		prefix:          settings.BucketPrefix,
		region:          settings.Region,
		presignLifetime: settings.PresignLifetime,
	}, nil
}

// presigner returns the client that signs for a given audience.
func (b *Blobs) presigner(audience Audience) *minio.Client {
	if audience == Internal {
		return b.client
	}
	return b.signer
}

// bucketName maps a domain bucket to its name in the store, so that several
// installations can share one store without colliding.
func (b *Blobs) bucketName(bucket domain.Bucket) string {
	if b.prefix == "" {
		return string(bucket)
	}
	return b.prefix + "-" + string(bucket)
}

// EnsureBuckets creates any bucket that does not yet exist. It is called by the
// migration command, not by a serving process, so that a running service never
// changes the shape of storage.
func (b *Blobs) EnsureBuckets(ctx context.Context) ([]string, error) {
	var created []string
	for _, bucket := range []domain.Bucket{domain.Evidence, domain.Derived, domain.Ephemeral} {
		name := b.bucketName(bucket)
		exists, err := b.client.BucketExists(ctx, name)
		if err != nil {
			return created, fmt.Errorf("checking for bucket %s: %w", name, err)
		}
		if exists {
			continue
		}
		if err := b.client.MakeBucket(ctx, name, minio.MakeBucketOptions{Region: b.region}); err != nil {
			return created, fmt.Errorf("creating bucket %s: %w", name, err)
		}
		created = append(created, name)
	}
	return created, nil
}

// Reachable reports whether the object store answers, which readiness depends
// on.
func (b *Blobs) Reachable(ctx context.Context) error {
	if _, err := b.client.BucketExists(ctx, b.bucketName(domain.Evidence)); err != nil {
		return fmt.Errorf("reaching the object store: %w", err)
	}
	return nil
}

// ContentKey is where bytes of a given digest live. Two identical uploads
// occupy one key, so deduplication is a property of addressing rather than a
// feature that must be maintained.
func ContentKey(digest domain.Digest) string {
	text := digest.String()
	return text[0:2] + "/" + text
}

// stagingKey is where bytes live between arriving and being verified. Unverified
// bytes never occupy a content address, so a content address always holds what
// it claims.
func stagingKey(grantID string) string { return "_staging/" + grantID }

// PresignPut returns a short-lived URL that accepts exactly one upload into
// staging.
func (b *Blobs) PresignPut(ctx context.Context, bucket domain.Bucket, grantID string, audience Audience) (string, error) {
	target, err := b.presigner(audience).PresignedPutObject(ctx, b.bucketName(bucket), stagingKey(grantID), b.presignLifetime)
	if err != nil {
		return "", fmt.Errorf("issuing an upload grant: %w", err)
	}
	return target.String(), nil
}

// PresignGet returns a short-lived URL that reads one stored object.
func (b *Blobs) PresignGet(ctx context.Context, bucket domain.Bucket, digest domain.Digest, filename string, audience Audience) (string, error) {
	params := url.Values{}
	if filename != "" {
		params.Set("response-content-disposition", "attachment; filename=\""+filename+"\"")
	}
	target, err := b.presigner(audience).PresignedGetObject(ctx, b.bucketName(bucket), ContentKey(digest), b.presignLifetime, params)
	if err != nil {
		return "", fmt.Errorf("issuing a read grant: %w", err)
	}
	return target.String(), nil
}

// VerifyStaged reads what was uploaded and reports its true digest and size.
// This is the point at which a client's claim about its own bytes is checked.
func (b *Blobs) VerifyStaged(ctx context.Context, bucket domain.Bucket, grantID string) (domain.Digest, int64, error) {
	object, err := b.client.GetObject(ctx, b.bucketName(bucket), stagingKey(grantID), minio.GetObjectOptions{})
	if err != nil {
		return domain.Digest{}, 0, fmt.Errorf("reading the uploaded bytes: %w", err)
	}
	defer object.Close()

	hasher := sha256.New()
	size, err := io.Copy(hasher, object)
	if err != nil {
		return domain.Digest{}, 0, fmt.Errorf("reading the uploaded bytes: %w", err)
	}
	digest, err := domain.DigestFromBytes(hasher.Sum(nil))
	if err != nil {
		return domain.Digest{}, 0, err
	}
	return digest, size, nil
}

// PromoteStaged moves verified bytes to their content address.
func (b *Blobs) PromoteStaged(ctx context.Context, bucket domain.Bucket, grantID string, digest domain.Digest) error {
	name := b.bucketName(bucket)
	_, err := b.client.CopyObject(ctx,
		minio.CopyDestOptions{Bucket: name, Object: ContentKey(digest)},
		minio.CopySrcOptions{Bucket: name, Object: stagingKey(grantID)})
	if err != nil {
		return fmt.Errorf("placing verified bytes at their content address: %w", err)
	}
	return b.DiscardStaged(ctx, bucket, grantID)
}

// DiscardStaged removes bytes that were never verified, so that a rejected
// upload leaves nothing behind.
func (b *Blobs) DiscardStaged(ctx context.Context, bucket domain.Bucket, grantID string) error {
	err := b.client.RemoveObject(ctx, b.bucketName(bucket), stagingKey(grantID), minio.RemoveObjectOptions{})
	if err != nil {
		return fmt.Errorf("discarding staged bytes: %w", err)
	}
	return nil
}

// Put writes bytes directly at their content address. It is used by processes
// that already hold the bytes, such as the migration command seeding fixtures.
func (b *Blobs) Put(ctx context.Context, bucket domain.Bucket, digest domain.Digest, body io.Reader, size int64, mediaType string) error {
	_, err := b.client.PutObject(ctx, b.bucketName(bucket), ContentKey(digest), body, size,
		minio.PutObjectOptions{ContentType: mediaType})
	if err != nil {
		return fmt.Errorf("writing an object: %w", err)
	}
	return nil
}

// Open reads a stored object.
func (b *Blobs) Open(ctx context.Context, bucket domain.Bucket, digest domain.Digest) (io.ReadCloser, error) {
	object, err := b.client.GetObject(ctx, b.bucketName(bucket), ContentKey(digest), minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("reading an object: %w", err)
	}
	return object, nil
}

// ── bytes that arrive in parts ──────────────────────────────────────────────
//
// A video of a dive is gigabytes, and an upload that size over a home or a
// ship's connection drops. The store's multipart upload holds each part as it
// arrives, so the client asks what arrived and sends only what did not. The
// parts are assembled into staging, and from there verified and promoted like
// any other upload.

// Part is one part of a multipart upload that the store holds.
type Part struct {
	Number    int    `json:"number"`
	SizeBytes int64  `json:"sizeBytes"`
	ETag      string `json:"-"`
}

func (b *Blobs) core() minio.Core { return minio.Core{Client: b.client} }

// StartParts opens a multipart upload into a grant's staging key.
func (b *Blobs) StartParts(ctx context.Context, bucket domain.Bucket, grantID string) (string, error) {
	id, err := b.core().NewMultipartUpload(ctx, b.bucketName(bucket), stagingKey(grantID), minio.PutObjectOptions{})
	if err != nil {
		return "", fmt.Errorf("opening a multipart upload: %w", err)
	}
	return id, nil
}

// PutPart stores one part. Sending a part again replaces it.
func (b *Blobs) PutPart(ctx context.Context, bucket domain.Bucket, grantID, uploadID string, number int, body io.Reader, size int64) error {
	_, err := b.core().PutObjectPart(ctx, b.bucketName(bucket), stagingKey(grantID), uploadID, number, body, size,
		minio.PutObjectPartOptions{})
	if err != nil {
		return fmt.Errorf("storing part %d: %w", number, err)
	}
	return nil
}

// Parts lists the parts the store holds for an upload, in order.
func (b *Blobs) Parts(ctx context.Context, bucket domain.Bucket, grantID, uploadID string) ([]Part, error) {
	var parts []Part
	marker := 0
	for {
		listed, err := b.core().ListObjectParts(ctx, b.bucketName(bucket), stagingKey(grantID), uploadID, marker, 1000)
		if err != nil {
			return nil, fmt.Errorf("listing the parts that arrived: %w", err)
		}
		for _, p := range listed.ObjectParts {
			parts = append(parts, Part{Number: p.PartNumber, SizeBytes: p.Size, ETag: p.ETag})
		}
		if !listed.IsTruncated {
			return parts, nil
		}
		marker = listed.NextPartNumberMarker
	}
}

// FinishParts assembles the parts into the grant's staging key.
func (b *Blobs) FinishParts(ctx context.Context, bucket domain.Bucket, grantID, uploadID string, parts []Part) error {
	complete := make([]minio.CompletePart, len(parts))
	for i, p := range parts {
		complete[i] = minio.CompletePart{PartNumber: p.Number, ETag: p.ETag}
	}
	if _, err := b.core().CompleteMultipartUpload(ctx, b.bucketName(bucket), stagingKey(grantID), uploadID,
		complete, minio.PutObjectOptions{}); err != nil {
		return fmt.Errorf("assembling the parts: %w", err)
	}
	return nil
}

// AbandonParts throws away a multipart upload that will not be finished.
func (b *Blobs) AbandonParts(ctx context.Context, bucket domain.Bucket, grantID, uploadID string) error {
	if err := b.core().AbortMultipartUpload(ctx, b.bucketName(bucket), stagingKey(grantID), uploadID); err != nil {
		return fmt.Errorf("abandoning a multipart upload: %w", err)
	}
	return nil
}

// PutStaged writes a single-part upload into staging through this process,
// for a client that cannot reach the store directly.
func (b *Blobs) PutStaged(ctx context.Context, bucket domain.Bucket, grantID string, body io.Reader, size int64) error {
	if _, err := b.client.PutObject(ctx, b.bucketName(bucket), stagingKey(grantID), body, size,
		minio.PutObjectOptions{}); err != nil {
		return fmt.Errorf("storing the upload: %w", err)
	}
	return nil
}

// StagedSize reports the size of what is in a grant's staging key, or -1 when
// nothing is.
func (b *Blobs) StagedSize(ctx context.Context, bucket domain.Bucket, grantID string) (int64, error) {
	info, err := b.client.StatObject(ctx, b.bucketName(bucket), stagingKey(grantID), minio.StatObjectOptions{})
	if err != nil {
		if minio.ToErrorResponse(err).Code == "NoSuchKey" {
			return -1, nil
		}
		return 0, fmt.Errorf("looking at the upload: %w", err)
	}
	return info.Size, nil
}

// Remove deletes stored bytes from their content address. Only the collector
// calls it, after the record of the object is gone.
func (b *Blobs) Remove(ctx context.Context, bucket domain.Bucket, digest domain.Digest) error {
	if err := b.client.RemoveObject(ctx, b.bucketName(bucket), ContentKey(digest), minio.RemoveObjectOptions{}); err != nil {
		return fmt.Errorf("removing stored bytes: %w", err)
	}
	return nil
}
