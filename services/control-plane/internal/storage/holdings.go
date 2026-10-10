package storage

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// What an organisation may store, how bytes arrive in parts, and how an
// object nobody wants any more is collected.

const (
	// DefaultPartBytes is how large each part of a multipart upload is. A
	// part is what is sent again after a drop, so it is small enough to resend
	// over a poor connection (a minute at five megabits) and large enough that
	// a 4 GB video is a hundred and some of them.
	DefaultPartBytes = int64(32) << 20
	// DefaultPartsLifetime is how long a multipart upload may take, drops
	// and all.
	DefaultPartsLifetime = 24 * time.Hour
	// DefaultOrgLimitBytes is what an organisation may hold when nobody set
	// its limit: a few surveys and an hour or two of dive video.
	DefaultOrgLimitBytes = int64(200) << 30
)

// PartPlan says how an upload is cut into parts: Count parts of PartBytes,
// the last one whatever is left.
type PartPlan struct {
	Count     int   `json:"count"`
	PartBytes int64 `json:"partBytes"`
}

func partCount(size, partBytes int64) int {
	if size <= partBytes {
		return 1
	}
	return int((size + partBytes - 1) / partBytes)
}

func planParts(size, partBytes int64) PartPlan {
	count := partCount(size, partBytes)
	if count == 1 {
		return PartPlan{Count: 1, PartBytes: size}
	}
	return PartPlan{Count: count, PartBytes: partBytes}
}

// partSize is how many bytes part `number` (from 1) of an upload carries.
func partSize(plan PartPlan, size int64, number int) int64 {
	if number < plan.Count {
		return plan.PartBytes
	}
	return size - int64(plan.Count-1)*plan.PartBytes
}

// missingParts lists the parts not yet held in full, in order.
func missingParts(held []Part, plan PartPlan, size int64) []int {
	have := make(map[int]int64, len(held))
	for _, p := range held {
		have[p.Number] = p.SizeBytes
	}
	var missing []int
	for n := 1; n <= plan.Count; n++ {
		if got, ok := have[n]; !ok || got != partSize(plan, size, n) {
			missing = append(missing, n)
		}
	}
	return missing
}

// PartsMissing reports an upload confirmed before all its parts arrived.
type PartsMissing struct {
	Missing []int
	Of      int
}

func (e *PartsMissing) Error() string {
	return fmt.Sprintf("%d of %d parts have not arrived", len(e.Missing), e.Of)
}

// OverLimit reports an upload that would take an organisation past what it
// may hold.
type OverLimit struct {
	UsedBytes, LimitBytes, AskedBytes int64
}

func (e *OverLimit) Error() string {
	return fmt.Sprintf("this organisation holds %d of its %d bytes; %d more does not fit",
		e.UsedBytes, e.LimitBytes, e.AskedBytes)
}

// fits says whether an upload of `asked` bytes fits beside what is held and
// what is already on its way.
func fits(used, onTheWay, limit, asked int64) bool {
	return used+onTheWay+asked <= limit
}

// Usage is what an organisation holds against what it may.
type Usage struct {
	OrgID         string `json:"orgId"`
	UsedBytes     int64  `json:"usedBytes"`
	Objects       int64  `json:"objects"`
	OnTheWayBytes int64  `json:"onTheWayBytes"`
	LimitBytes    int64  `json:"limitBytes"`
	LimitSet      bool   `json:"limitSet"`
}

// Usage reads an organisation's holdings, its open uploads and its limit.
func (o *Objects) Usage(ctx context.Context, orgID string) (Usage, error) {
	usage := Usage{OrgID: orgID, LimitBytes: o.defaultLimit}
	err := o.pool.QueryRow(ctx, `
		SELECT coalesce(sum(o.size_bytes), 0), count(*)
		FROM store.holding h JOIN store.object o ON o.id = h.object_id
		WHERE h.org_id = $1`, orgID).Scan(&usage.UsedBytes, &usage.Objects)
	if err != nil {
		return Usage{}, fmt.Errorf("reading what an organisation holds: %w", err)
	}
	err = o.pool.QueryRow(ctx, `
		SELECT coalesce(sum(declared_size), 0) FROM store.upload_grant
		WHERE org_id = $1 AND confirmed_at IS NULL AND expires_at > now()`, orgID).Scan(&usage.OnTheWayBytes)
	if err != nil {
		return Usage{}, fmt.Errorf("reading an organisation's open uploads: %w", err)
	}
	var limit int64
	err = o.pool.QueryRow(ctx, `SELECT max_bytes FROM store.quota WHERE org_id = $1`, orgID).Scan(&limit)
	switch {
	case err == nil:
		usage.LimitBytes, usage.LimitSet = limit, true
	case !errors.Is(db.Translate(err), db.ErrNotFound):
		return Usage{}, fmt.Errorf("reading an organisation's limit: %w", err)
	}
	return usage, nil
}

// roomFor refuses an upload that would not fit. Bytes the organisation
// already holds cost it nothing more.
func (o *Objects) roomFor(ctx context.Context, orgID string, bucket domain.Bucket, digest domain.Digest, size int64) error {
	var held bool
	if err := o.pool.QueryRow(ctx, `
		SELECT EXISTS (
		    SELECT 1 FROM store.holding h JOIN store.object o ON o.id = h.object_id
		    WHERE h.org_id = $1 AND o.bucket = $2::store.bucket AND o.sha256 = $3)`,
		orgID, string(bucket), digest.Bytes()).Scan(&held); err != nil {
		return fmt.Errorf("checking what an organisation holds: %w", err)
	}
	if held {
		return nil
	}
	usage, err := o.Usage(ctx, orgID)
	if err != nil {
		return err
	}
	if !fits(usage.UsedBytes, usage.OnTheWayBytes, usage.LimitBytes, size) {
		return &OverLimit{UsedBytes: usage.UsedBytes + usage.OnTheWayBytes, LimitBytes: usage.LimitBytes, AskedBytes: size}
	}
	return nil
}

// SetLimit sets what an organisation may hold.
func (o *Objects) SetLimit(ctx context.Context, principalID, orgID string, limitBytes int64) error {
	if limitBytes < 0 {
		return fmt.Errorf("%w: a limit is not negative", domain.ErrInvalid)
	}
	_, err := o.pool.Exec(ctx, `
		INSERT INTO store.quota (org_id, max_bytes, set_by) VALUES ($1, $2, $3)
		ON CONFLICT (org_id) DO UPDATE SET max_bytes = $2, set_by = $3, set_at = now()`,
		orgID, limitBytes, principalID)
	if err != nil {
		return fmt.Errorf("setting an organisation's limit: %w", err)
	}
	return nil
}

// openGrant is what sending a part needs to know about its grant.
type openGrant struct {
	bucket      domain.Bucket
	size        int64
	orgID       string
	multipartID string
	plan        PartPlan
}

func (o *Objects) open(ctx context.Context, principalID, orgID, grantID string) (openGrant, error) {
	var (
		g           openGrant
		issuedTo    string
		grantOrg    *string
		multipartID *string
		partBytes   *int64
		expiresAt   time.Time
		confirmedAt *time.Time
	)
	err := o.pool.QueryRow(ctx, `
		SELECT bucket, declared_size, issued_to, org_id, multipart_id, part_bytes, expires_at, confirmed_at
		FROM store.upload_grant WHERE id = $1`, grantID).
		Scan(&g.bucket, &g.size, &issuedTo, &grantOrg, &multipartID, &partBytes, &expiresAt, &confirmedAt)
	if err != nil {
		return openGrant{}, db.Translate(err)
	}
	if issuedTo != principalID || grantOrg == nil || *grantOrg != orgID {
		return openGrant{}, db.ErrNotFound
	}
	if confirmedAt != nil || time.Now().After(expiresAt) {
		return openGrant{}, ErrGrantSpent
	}
	g.orgID = *grantOrg
	if multipartID != nil {
		g.multipartID = *multipartID
		g.plan = PartPlan{Count: partCount(g.size, *partBytes), PartBytes: *partBytes}
	} else {
		g.plan = PartPlan{Count: 1, PartBytes: g.size}
	}
	return g, nil
}

// PutPart stores one part of an upload, sent through the API. A part sent
// again replaces the one before.
func (o *Objects) PutPart(ctx context.Context, principalID, orgID, grantID string, number int, body io.Reader, size int64) error {
	g, err := o.open(ctx, principalID, orgID, grantID)
	if err != nil {
		return err
	}
	if number < 1 || number > g.plan.Count {
		return fmt.Errorf("%w: this upload has parts 1 to %d", domain.ErrInvalid, g.plan.Count)
	}
	if want := partSize(g.plan, g.size, number); size != want {
		return fmt.Errorf("%w: part %d is %d bytes, not %d", domain.ErrInvalid, number, want, size)
	}
	body = io.LimitReader(body, size)
	if g.multipartID == "" {
		return o.blobs.PutStaged(ctx, g.bucket, grantID, body, size)
	}
	return o.blobs.PutPart(ctx, g.bucket, grantID, g.multipartID, number, body, size)
}

// Progress is what has arrived of an upload, so a client resumes it.
type Progress struct {
	GrantID   string    `json:"grantId"`
	SizeBytes int64     `json:"sizeBytes"`
	Parts     PartPlan  `json:"parts"`
	Arrived   []Part    `json:"arrived"`
	Missing   []int     `json:"missing"`
	ExpiresAt time.Time `json:"expiresAt,omitempty"`
}

// Progress reads which parts of an upload have arrived.
func (o *Objects) Progress(ctx context.Context, principalID, orgID, grantID string) (Progress, error) {
	g, err := o.open(ctx, principalID, orgID, grantID)
	if err != nil {
		return Progress{}, err
	}
	var arrived []Part
	if g.multipartID != "" {
		if arrived, err = o.blobs.Parts(ctx, g.bucket, grantID, g.multipartID); err != nil {
			return Progress{}, err
		}
	} else {
		staged, err := o.blobs.StagedSize(ctx, g.bucket, grantID)
		if err != nil {
			return Progress{}, err
		}
		if staged >= 0 {
			arrived = []Part{{Number: 1, SizeBytes: staged}}
		}
	}
	if arrived == nil {
		arrived = []Part{}
	}
	missing := missingParts(arrived, g.plan, g.size)
	if missing == nil {
		missing = []int{}
	}
	return Progress{GrantID: grantID, SizeBytes: g.size, Parts: g.plan, Arrived: arrived, Missing: missing}, nil
}

// Holding is one object an organisation holds.
type Holding struct {
	Object
	HeldBy    string    `json:"heldBy"`
	HeldSince time.Time `json:"heldSince"`
}

// Holdings lists what an organisation holds, newest first.
func (o *Objects) Holdings(ctx context.Context, orgID string, limit int) ([]Holding, error) {
	if limit <= 0 || limit > 1000 {
		limit = 200
	}
	rows, err := o.pool.Query(ctx, `
		SELECT o.id, o.bucket, o.sha256, o.size_bytes, o.media_type, o.uploaded_by, o.uploaded_at,
		       h.held_by, h.held_since
		FROM store.holding h JOIN store.object o ON o.id = h.object_id
		WHERE h.org_id = $1 ORDER BY h.held_since DESC LIMIT $2`, orgID, limit)
	if err != nil {
		return nil, fmt.Errorf("listing what an organisation holds: %w", err)
	}
	defer rows.Close()
	held := []Holding{}
	for rows.Next() {
		var h Holding
		var raw []byte
		if err := rows.Scan(&h.ID, &h.Bucket, &raw, &h.SizeBytes, &h.MediaType, &h.UploadedBy,
			&h.UploadedAt, &h.HeldBy, &h.HeldSince); err != nil {
			return nil, err
		}
		if h.Digest, err = domain.DigestFromBytes(raw); err != nil {
			return nil, err
		}
		h.SHA256 = h.Digest.String()
		held = append(held, h)
	}
	return held, rows.Err()
}

// Released says what letting go of an object did.
type Released struct {
	ObjectID  string `json:"objectId"`
	Collected bool   `json:"collected"`
	// Why the bytes stay, when they do.
	KeptBecause string `json:"keptBecause,omitempty"`
	FreedBytes  int64  `json:"freedBytes"`
}

// Release lets an organisation go of an object, and collects the object when
// nobody holds it and nothing refers to it.
func (o *Objects) Release(ctx context.Context, orgID, objectID string) (Released, error) {
	object, err := o.Object(ctx, objectID)
	if err != nil {
		return Released{}, err
	}
	tag, err := o.pool.Exec(ctx, `DELETE FROM store.holding WHERE org_id = $1 AND object_id = $2`, orgID, objectID)
	if err != nil {
		return Released{}, fmt.Errorf("letting go of an object: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return Released{}, db.ErrNotFound
	}
	released := Released{ObjectID: objectID, FreedBytes: object.SizeBytes}
	released.KeptBecause, err = o.collect(ctx, object)
	if err != nil {
		return Released{}, err
	}
	released.Collected = released.KeptBecause == ""
	return released, nil
}

// collect removes an object nobody holds and nothing refers to, record and
// bytes, and says why when it cannot.
func (o *Objects) collect(ctx context.Context, object Object) (string, error) {
	kept := ""
	err := o.pool.InTransaction(ctx, func(conn db.Conn) error {
		var heldElsewhere, anInput bool
		if err := conn.QueryRow(ctx, `
			SELECT EXISTS (SELECT 1 FROM store.holding WHERE object_id = $1),
			       EXISTS (SELECT 1 FROM exec.job
			               WHERE inputs @> jsonb_build_array(jsonb_build_object('objectId', $1::text)))`,
			object.ID).Scan(&heldElsewhere, &anInput); err != nil {
			return err
		}
		switch {
		case heldElsewhere:
			kept = "another organisation holds the same bytes"
			return nil
		case anInput:
			kept = "a job was given it as an input"
			return nil
		}
		if _, err := conn.Exec(ctx, `SET LOCAL store.collecting = 'on'`); err != nil {
			return err
		}
		_, err := conn.Exec(ctx, `DELETE FROM store.object WHERE id = $1`, object.ID)
		if db.IsForeignKeyViolation(err) {
			kept = "a place version, a run or a job's output is made of it"
			return errKept
		}
		return err
	})
	if errors.Is(err, errKept) {
		return kept, nil
	}
	if err != nil {
		return "", fmt.Errorf("collecting an object: %w", err)
	}
	if kept != "" {
		return kept, nil
	}
	if err := o.blobs.Remove(ctx, object.Bucket, object.Digest); err != nil {
		return "", err
	}
	return "", nil
}

// errKept rolls back a collection that something still refers to.
var errKept = errors.New("kept: something refers to it")

// Ingest records bytes the platform made on an organisation's behalf (a place
// a build produced): hashed here, stored at their content address, held by the
// organisation. The same bytes already stored are not stored again.
func (o *Objects) Ingest(ctx context.Context, principalID, orgID string, bucket domain.Bucket,
	body io.ReadSeeker, size int64, mediaType string) (Object, error) {
	hasher := sha256.New()
	if _, err := io.Copy(hasher, body); err != nil {
		return Object{}, fmt.Errorf("hashing what was made: %w", err)
	}
	digest, err := domain.DigestFromBytes(hasher.Sum(nil))
	if err != nil {
		return Object{}, err
	}
	object, err := o.ByDigest(ctx, bucket, digest)
	if errors.Is(err, db.ErrNotFound) {
		if _, err := body.Seek(0, io.SeekStart); err != nil {
			return Object{}, err
		}
		if err := o.blobs.Put(ctx, bucket, digest, body, size, mediaType); err != nil {
			return Object{}, err
		}
		object = Object{ID: ids.New(ids.KindObject), Bucket: bucket, Digest: digest, SHA256: digest.String(),
			SizeBytes: size, MediaType: mediaType, UploadedBy: principalID}
		err = o.pool.QueryRow(ctx, `
			INSERT INTO store.object (id, bucket, sha256, size_bytes, media_type, uploaded_by)
			VALUES ($1, $2::store.bucket, $3, $4, $5, $6)
			ON CONFLICT (bucket, sha256) DO UPDATE SET id = store.object.id
			RETURNING id, uploaded_at`,
			object.ID, string(bucket), digest.Bytes(), size, mediaType, principalID).
			Scan(&object.ID, &object.UploadedAt)
	}
	if err != nil {
		return Object{}, fmt.Errorf("recording what was made: %w", err)
	}
	if orgID != "" {
		if _, err := o.pool.Exec(ctx, `
			INSERT INTO store.holding (org_id, object_id, held_by) VALUES ($1, $2, $3)
			ON CONFLICT DO NOTHING`, orgID, object.ID, principalID); err != nil {
			return Object{}, fmt.Errorf("holding what was made: %w", err)
		}
	}
	return object, nil
}
