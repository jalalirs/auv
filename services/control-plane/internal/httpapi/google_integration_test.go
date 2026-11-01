//go:build integration

package httpapi

// Google sign-in against a real record. Google itself is not called: the
// account it would have vouched for is handed straight to signInGoogle.
//
//	IOCEAN_TEST_DATABASE_URL=postgres://... go test -tags integration -run Google ./internal/httpapi/
//
// It writes people and organisations with addresses under .test, into a
// record that is thrown away afterwards.

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"slices"
	"testing"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

func TestGoogleSignInMakesASpaceAndFollowsApprovals(t *testing.T) {
	url := os.Getenv("IOCEAN_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("IOCEAN_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	pool, err := db.Open(ctx, url, 4)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	d := &Dependencies{
		Pool: pool, Identity: identity.NewStore(pool, time.Hour), Authorizer: policy.NewAuthorizer(pool),
		Audit: audit.NewRecorder(), Broker: exec.NewBroker(pool),
		Logger:   slog.New(slog.NewTextHandler(io.Discard, nil)),
		Personal: PersonalStart{DivesMonthly: 10, DailyCap: 100},
	}
	run := ids.New(ids.KindRun)[4:14] // a fresh suffix, so the test can run again on the same record
	account := func(local, domain, hd string) identity.GoogleAccount {
		return identity.GoogleAccount{Subject: "g-" + local + "-" + run, Email: local + "-" + run + "@" + domain,
			EmailVerified: true, HostedDomain: hd, Name: local}
	}
	orgsOf := func(principalID string) []string {
		orgs, err := d.Identity.OrganisationsOf(ctx, principalID)
		if err != nil {
			t.Fatal(err)
		}
		return orgs
	}
	personalOf := func(principalID string) string {
		var orgID string
		if err := pool.QueryRow(ctx, `SELECT id FROM identity.organisation WHERE personal_of = $1`,
			principalID).Scan(&orgID); err != nil {
			t.Fatalf("no personal organisation for %s: %v", principalID, err)
		}
		return orgID
	}

	// A first sign-in makes a person and their own organisation, with ten dives a month.
	ali := account("ali", "inst.test", "")
	aliID, err := d.signInGoogle(ctx, ali)
	if err != nil {
		t.Fatal(err)
	}
	aliSpace := personalOf(aliID)
	quota, _, err := d.Broker.Quota(ctx, aliSpace)
	if err != nil || quota.MaxDivesMonthly == nil || *quota.MaxDivesMonthly != 10 {
		t.Fatalf("personal quota %+v, %v", quota, err)
	}
	if got := orgsOf(aliID); !slices.Equal(got, []string{aliSpace}) {
		t.Fatalf("ali belongs to %v, want only %s", got, aliSpace)
	}
	// And signing in again is the same person, with the same one space.
	again, err := d.signInGoogle(ctx, ali)
	if err != nil || again != aliID {
		t.Fatalf("second sign-in gave %s, %v", again, err)
	}

	// An institution approves an address before its owner ever signs in.
	var inst identity.Organisation
	if err := pool.InTransaction(ctx, func(conn db.Conn) error {
		inst, err = d.Identity.CreateOrganisation(ctx, conn, "inst-"+lower(run), "Institution")
		if err != nil {
			return err
		}
		bea := account("bea", "inst.test", "")
		_, err = d.Identity.ApproveEmail(ctx, conn, inst.ID, bea.Email, aliID)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	beaID, err := d.signInGoogle(ctx, account("bea", "inst.test", ""))
	if err != nil {
		t.Fatal(err)
	}
	if got := orgsOf(beaID); !slices.Contains(got, inst.ID) || !slices.Contains(got, personalOf(beaID)) {
		t.Fatalf("bea belongs to %v, want the institution and her own space", got)
	}

	// A domain matches a Workspace account in it, and not a personal account
	// that merely uses an address there.
	domain := "inst-" + lower(run) + ".test"
	if err := pool.InTransaction(ctx, func(conn db.Conn) error {
		_, err := d.Identity.ApproveDomain(ctx, conn, inst.ID, domain, aliID)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	caiID, _ := d.signInGoogle(ctx, account("cai", domain, domain))
	danID, _ := d.signInGoogle(ctx, account("dan", domain, ""))
	if !slices.Contains(orgsOf(caiID), inst.ID) {
		t.Error("a Workspace account in an approved domain was not made a member")
	}
	if slices.Contains(orgsOf(danID), inst.ID) {
		t.Error("an account outside the Workspace was made a member by its address alone")
	}

	// Withdrawing the address withdraws the membership at once.
	if err := pool.InTransaction(ctx, func(conn db.Conn) error {
		return d.Identity.WithdrawEmail(ctx, conn, inst.ID, account("bea", "inst.test", "").Email)
	}); err != nil {
		t.Fatal(err)
	}
	if slices.Contains(orgsOf(beaID), inst.ID) {
		t.Error("bea is still a member after her address was withdrawn")
	}

	// A personal space takes no approvals.
	if err := pool.InTransaction(ctx, func(conn db.Conn) error {
		_, err := d.Identity.ApproveEmail(ctx, conn, aliSpace, "x-"+run+"@inst.test", aliID)
		return err
	}); !errors.Is(err, identity.ErrPersonalOrganisation) {
		t.Errorf("approving an address on a personal space gave %v", err)
	}

	// An unverified address is refused.
	unverified := account("eve", "inst.test", "")
	unverified.EmailVerified = false
	if _, err := d.signInGoogle(ctx, unverified); !errors.Is(err, identity.ErrUnverifiedEmail) {
		t.Errorf("an unverified address gave %v", err)
	}

	// The day's cap holds for new people, and not for people already known.
	d.Personal.DailyCap = 1
	if _, err := d.signInGoogle(ctx, account("fay", "inst.test", "")); !errors.Is(err, errPersonalCapReached) {
		t.Errorf("a new person past the day's cap gave %v", err)
	}
	if _, err := d.signInGoogle(ctx, ali); err != nil {
		t.Errorf("a known person past the day's cap was refused: %v", err)
	}

	// Someone an administrator registered with a secret, signing in with
	// Google under the same address, is the same person and gets a space.
	var admin identity.Principal
	if err := pool.InTransaction(ctx, func(conn db.Conn) error {
		admin, err = d.Identity.CreatePerson(ctx, conn, identity.PersonSpec{
			DisplayName: "Gus", Email: "gus-" + run + "@inst.test", Secret: "a-long-enough-secret"})
		return err
	}); err != nil {
		t.Fatal(err)
	}
	gus := account("gus", "inst.test", "")
	if id, err := d.signInGoogle(ctx, gus); err != nil || id != admin.ID {
		t.Fatalf("gus signing in with Google gave %s, %v; want %s", id, err, admin.ID)
	}
	personalOf(admin.ID)

	// A hand-off code is good once.
	code, err := d.Identity.CreateHandoff(ctx, aliID)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, principal, err := d.Identity.RedeemHandoff(ctx, code); err != nil || principal.ID != aliID {
		t.Fatalf("redeeming gave %v, %v", principal.ID, err)
	}
	if _, _, _, err := d.Identity.RedeemHandoff(ctx, code); !errors.Is(err, identity.ErrUnauthenticated) {
		t.Errorf("a second redemption gave %v", err)
	}
}

func lower(s string) string {
	out := []byte(s)
	for i, c := range out {
		if c >= 'A' && c <= 'Z' {
			out[i] = c + 'a' - 'A'
		}
	}
	return string(out)
}

func TestAnAdminEmailMakesAPlatformAdministratorOnce(t *testing.T) {
	url := os.Getenv("IOCEAN_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("IOCEAN_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	pool, err := db.Open(ctx, url, 4)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	run := ids.New(ids.KindRun)[4:14]
	boss := identity.GoogleAccount{Subject: "g-boss-" + run, Email: "Boss-" + run + "@inst.test",
		EmailVerified: true, Name: "boss"}
	other := identity.GoogleAccount{Subject: "g-other-" + run, Email: "other-" + run + "@inst.test",
		EmailVerified: true, Name: "other"}
	d := &Dependencies{
		Pool: pool, Identity: identity.NewStore(pool, time.Hour), Authorizer: policy.NewAuthorizer(pool),
		Audit: audit.NewRecorder(), Broker: exec.NewBroker(pool),
		Logger:   slog.New(slog.NewTextHandler(io.Discard, nil)),
		Personal: PersonalStart{DivesMonthly: 10, DailyCap: 100},
		// Listed in lower case, as config.Load leaves it; Google may say it otherwise.
		Google: GoogleSignIn{Admins: []string{"boss-" + lower(run) + "@inst.test"}},
	}
	admins := func(principalID string) int {
		var n int
		if err := pool.QueryRow(ctx, `
			SELECT count(*) FROM policy.binding
			 WHERE subject_kind = 'principal' AND subject_id = $1
			   AND scope_kind = 'platform' AND role = 'admin' AND revoked_at IS NULL`, principalID).Scan(&n); err != nil {
			t.Fatal(err)
		}
		return n
	}

	bossID, err := d.signInGoogle(ctx, boss)
	if err != nil {
		t.Fatal(err)
	}
	if again, err := d.signInGoogle(ctx, boss); err != nil || again != bossID {
		t.Fatalf("second sign-in gave %s, %v", again, err)
	}
	if n := admins(bossID); n != 1 {
		t.Errorf("a listed address has %d platform admin bindings after two sign-ins, want 1", n)
	}
	otherID, err := d.signInGoogle(ctx, other)
	if err != nil {
		t.Fatal(err)
	}
	if n := admins(otherID); n != 0 {
		t.Errorf("an address not on the list was made an administrator")
	}
}
