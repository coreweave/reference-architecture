package repair

import (
	"context"
	"fmt"
	"path"
)

func ExpectedPath(namespace, name string) (string, error) {
	if namespace == "" || name == "" || path.Base(namespace) != namespace || path.Base(name) != name {
		return "", fmt.Errorf("invalid PVC identity")
	}
	return HostRoot + "/kafka/" + namespace + "/" + name, nil
}

func Candidates(ctx context.Context, r Reader, allow Allowlist, localNode string) ([]Candidate, error) {
	if localNode == "" {
		return nil, fmt.Errorf("local node name is required")
	}
	pvs, err := r.ListPVs(ctx)
	if err != nil {
		return nil, err
	}
	var result []Candidate
	for _, pv := range pvs {
		if pv.Phase != "Bound" || pv.VolumeMode != "local" || pv.StorageClass != StorageClass || !pv.NodeAffinityValid || pv.NodeOperator != "In" || pv.ClaimNamespace == "" || pv.ClaimName == "" || pv.ClaimUID == "" || pv.NodeHostname == "" {
			continue
		}
		expected, err := ExpectedPath(pv.ClaimNamespace, pv.ClaimName)
		if err != nil || pv.LocalPath != expected {
			continue
		}
		pvc, err := r.GetPVC(ctx, pv.ClaimNamespace, pv.ClaimName)
		if err != nil || pvc.Phase != "Bound" || pvc.UID != pv.ClaimUID || pvc.VolumeName != pv.Name {
			continue
		}
		var node NodeIdentity
		for name, identity := range allow {
			if identity.Hostname == pv.NodeHostname {
				node, err = r.GetNode(ctx, name)
				break
			}
		}
		if err != nil || node.Name != localNode || VerifyIdentity(allow, node) != nil || node.Hostname != pv.NodeHostname {
			continue
		}
		result = append(result, Candidate{PV: pv, PVC: pvc, Node: node})
	}
	return result, nil
}
