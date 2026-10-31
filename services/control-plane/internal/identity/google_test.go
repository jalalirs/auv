package identity

import (
	"regexp"
	"testing"
)

// The slug rule identity.organisation enforces.
var slugRule = regexp.MustCompile(`^[a-z][a-z0-9-]{0,61}[a-z0-9]$`)

func TestAPersonalSlugIsAlwaysAValidLabel(t *testing.T) {
	for _, email := range []string{
		"ali@kaust.edu.sa", "Ali.Al-Harbi@x.com", "007@x.com", "___@x.com",
		"a-very-long-local-part-that-goes-on-and-on-and-on-forever@x.com",
	} {
		slug, err := personalSlug(email)
		if err != nil {
			t.Fatal(err)
		}
		if !slugRule.MatchString(slug) {
			t.Errorf("%s gave %q, which the schema refuses", email, slug)
		}
	}
	first, _ := personalSlug("ali@x.com")
	second, _ := personalSlug("ali@y.com")
	if first == second {
		t.Errorf("two people called ali got the same slug %q", first)
	}
}
