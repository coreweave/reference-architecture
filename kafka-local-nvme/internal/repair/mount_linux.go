//go:build linux

package repair

import (
	"fmt"
	"os"
	"sort"
	"strings"
)

func decodeMount(s string) string {
	return strings.NewReplacer(`\040`, " ", `\011`, "\t", `\012`, "\n", `\134`, `\`).Replace(s)
}
func normalizedOptions(s string) []string {
	m := map[string]bool{}
	for _, v := range strings.Split(s, ",") {
		if v != "" && v != "ro" && v != "rw" {
			m[v] = true
		}
	}
	out := make([]string, 0, len(m))
	for v := range m {
		out = append(out, v)
	}
	sort.Strings(out)
	return out
}
func sameOptions(a, b []string) bool {
	a = append([]string(nil), a...)
	b = append([]string(nil), b...)
	sort.Strings(a)
	sort.Strings(b)
	return strings.Join(a, ",") == strings.Join(b, ",")
}

// VerifyHostMount reads PID 1 mountinfo, so callers must use hostPID and a host /proc mount.
func VerifyHostMount(mountInfoPath string, want MountSignature) error {
	for _, option := range want.Options {
		if option == "ro" || option == "rw" {
			return fmt.Errorf("configured mount options must omit access mode")
		}
	}
	b, err := os.ReadFile(mountInfoPath)
	if err != nil {
		return err
	}
	var found []MountSignature
	nested := false
	for _, line := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		parts := strings.Split(line, " - ")
		if len(parts) != 2 {
			continue
		}
		left := strings.Fields(parts[0])
		right := strings.Fields(parts[1])
		if len(left) < 6 || len(right) < 3 {
			continue
		}
		mountPoint := decodeMount(left[4])
		if strings.HasPrefix(mountPoint, HostRoot+"/") {
			nested = true
			continue
		}
		if mountPoint != HostRoot {
			continue
		}
		rawOptions := left[5] + "," + right[2]
		for _, option := range strings.Split(rawOptions, ",") {
			if option == "ro" {
				return fmt.Errorf("host mount is read-only")
			}
		}
		found = append(found, MountSignature{Source: decodeMount(right[1]), FSType: right[0], Options: normalizedOptions(rawOptions)})
	}
	if nested {
		return fmt.Errorf("nested mount below %s", HostRoot)
	}
	if len(found) != 1 {
		return fmt.Errorf("expected one host mount for %s, found %d", HostRoot, len(found))
	}
	got := found[0]
	if got.Source != want.Source || got.FSType != want.FSType || !sameOptions(got.Options, normalizedOptions(strings.Join(want.Options, ","))) {
		return fmt.Errorf("host mount signature mismatch")
	}
	return nil
}
