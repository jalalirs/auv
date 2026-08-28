package platform

// Info is the public identity of the running Coral City control plane.
type Info struct {
	Name    string `json:"name"`
	Service string `json:"service"`
	Version string `json:"version"`
	Commit  string `json:"commit"`
	BuiltAt string `json:"builtAt"`
}

// Build returns normalized build metadata. Values may be replaced by linker
// flags in release builds.
func Build(version, commit, builtAt string) Info {
	return Info{
		Name:    "Coral City",
		Service: "control-plane",
		Version: fallback(version, "development"),
		Commit:  fallback(commit, "unknown"),
		BuiltAt: fallback(builtAt, "unknown"),
	}
}

func fallback(value, fallbackValue string) string {
	if value == "" {
		return fallbackValue
	}
	return value
}
