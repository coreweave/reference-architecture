package repair

import "fmt"

func VerifyIdentity(allowed Allowlist, live NodeIdentity) error {
	want, ok := allowed[live.Name]
	if !ok {
		return fmt.Errorf("node %q is not allowlisted", live.Name)
	}
	if live.Name == "" || live.Hostname == "" || live.UID == "" || live.ProviderID == "" {
		return fmt.Errorf("live node identity is incomplete")
	}
	if want.Name != live.Name || want.Hostname != live.Hostname || want.UID != live.UID || want.ProviderID == "" || want.ProviderID != live.ProviderID {
		return fmt.Errorf("node %q identity does not match immutable allowlist", live.Name)
	}
	return nil
}
