package domain

import (
	"fmt"
	"strings"
)

// ValidateRelativePath reports whether a path is safe to reproduce on any
// filesystem: relative, forward-slashed, with no traversal and no empty
// segments. The database enforces the same rule, so a path that reaches
// storage has passed both checks.
func ValidateRelativePath(path string) error {
	switch {
	case path == "":
		return fmt.Errorf("%w: a file within a version has a path", ErrInvalid)
	case strings.HasPrefix(path, "/"):
		return fmt.Errorf("%w: %q is absolute", ErrInvalid, path)
	case strings.Contains(path, `\`):
		return fmt.Errorf("%w: %q uses a backslash", ErrInvalid, path)
	case len(path) > 1024:
		return fmt.Errorf("%w: a path of %d characters is beyond any real filesystem",
			ErrInvalid, len(path))
	}
	for _, segment := range strings.Split(path, "/") {
		switch segment {
		case "":
			return fmt.Errorf("%w: %q has an empty segment", ErrInvalid, path)
		case ".", "..":
			return fmt.Errorf("%w: %q traverses outside its version", ErrInvalid, path)
		}
	}
	return nil
}

// ValidateSlug reports whether a name may be used in a URL as a stable,
// human-readable identifier for a city or a layer.
func ValidateSlug(slug string) error {
	if len(slug) < 2 || len(slug) > 63 {
		return fmt.Errorf("%w: a slug is between 2 and 63 characters, got %d", ErrInvalid, len(slug))
	}
	if slug[0] < 'a' || slug[0] > 'z' {
		return fmt.Errorf("%w: a slug begins with a lower-case letter, got %q", ErrInvalid, slug)
	}
	if last := slug[len(slug)-1]; last == '-' {
		return fmt.Errorf("%w: a slug ends in a letter or digit, got %q", ErrInvalid, slug)
	}
	for _, symbol := range slug {
		isLower := symbol >= 'a' && symbol <= 'z'
		isDigit := symbol >= '0' && symbol <= '9'
		if !isLower && !isDigit && symbol != '-' {
			return fmt.Errorf("%w: %q contains %q, which is not a lower-case letter, digit, or hyphen",
				ErrInvalid, slug, symbol)
		}
	}
	return nil
}
