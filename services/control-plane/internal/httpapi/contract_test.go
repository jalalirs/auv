package httpapi

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// contractPath is where the published description of this API lives. It is the
// source of truth for the shapes the platform accepts and returns; this file
// makes sure it is also true about which operations exist.
const contractPath = "../../../../packages/contracts/v1/openapi.yaml"

type contract struct {
	Paths map[string]map[string]struct {
		Summary  string `yaml:"summary"`
		Security []any  `yaml:"security"`
	} `yaml:"paths"`
}

func readContract(t *testing.T) contract {
	t.Helper()
	raw, err := os.ReadFile(filepath.Clean(contractPath))
	if err != nil {
		t.Fatalf("reading the contract: %v", err)
	}
	var document contract
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("parsing the contract: %v", err)
	}
	if len(document.Paths) == 0 {
		t.Fatal("the contract describes no operations")
	}
	return document
}

// contractOperations lists the contract as "METHOD /path".
func contractOperations(document contract) []string {
	var operations []string
	for path, methods := range document.Paths {
		for method := range methods {
			operations = append(operations, strings.ToUpper(method)+" "+path)
		}
	}
	slices.Sort(operations)
	return operations
}

// servedOperations lists the route table the same way.
//
// The multiplexer marks a trailing wildcard with an ellipsis; the contract
// names the same segment without one, because to a caller it is one path
// segment either way.
func servedOperations(t *testing.T) []string {
	var operations []string
	for _, route := range routeTable(t) {
		pattern := strings.ReplaceAll(route.Pattern, "...}", "}")
		operations = append(operations, route.Method+" "+pattern)
	}
	slices.Sort(operations)
	return operations
}

// TestTheContractDescribesEveryRoute is what keeps the published description
// true. A description that has drifted from the thing it describes is worse
// than none, so drift fails the build rather than waiting to be noticed.
func TestTheContractDescribesEveryRoute(t *testing.T) {
	served := servedOperations(t)
	described := contractOperations(readContract(t))

	for _, operation := range served {
		if !slices.Contains(described, operation) {
			t.Errorf("%s is served but the contract does not describe it", operation)
		}
	}
	for _, operation := range described {
		if !slices.Contains(served, operation) {
			t.Errorf("the contract describes %s but nothing serves it", operation)
		}
	}
}

// TestTheContractAgreesAboutWhatIsPublic keeps one list of endpoints that work
// before anyone is known. An operation that opts out of security in the
// contract but is guarded in the router — or the reverse — would mislead every
// reader of either.
func TestTheContractAgreesAboutWhatIsPublic(t *testing.T) {
	document := readContract(t)

	describedPublic := map[string]bool{}
	for path, methods := range document.Paths {
		for method, operation := range methods {
			// An empty security list is how an operation says it needs none.
			if operation.Security != nil && len(operation.Security) == 0 {
				describedPublic[strings.ToUpper(method)+" "+path] = true
			}
		}
	}

	for _, route := range routeTable(t) {
		name := route.Method + " " + strings.ReplaceAll(route.Pattern, "...}", "}")
		switch {
		case route.Public && !describedPublic[name]:
			t.Errorf("%s is served without credentials but the contract does not say so", name)
		case !route.Public && describedPublic[name]:
			t.Errorf("the contract says %s needs no credentials, but the router requires them", name)
		}
	}
}

// TestEveryDescribedOperationSaysWhatItIsFor keeps the contract readable as a
// description of the product rather than as a list of paths.
func TestEveryDescribedOperationSaysWhatItIsFor(t *testing.T) {
	for path, methods := range readContract(t).Paths {
		for method, operation := range methods {
			if strings.TrimSpace(operation.Summary) == "" {
				t.Errorf("%s %s has no summary in the contract", strings.ToUpper(method), path)
			}
		}
	}
}
