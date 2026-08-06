//go:build linux

package repair

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

type fakeReader struct {
	pvs    []PV
	pv     PV
	pvc    PVC
	node   NodeIdentity
	change bool
}

func (f *fakeReader) ListPVs(context.Context) ([]PV, error) { return f.pvs, nil }
func (f *fakeReader) GetPV(context.Context, string) (PV, error) {
	if f.change {
		x := f.pv
		x.ClaimUID = "changed"
		return x, nil
	}
	return f.pv, nil
}
func (f *fakeReader) GetPVC(context.Context, string, string) (PVC, error)   { return f.pvc, nil }
func (f *fakeReader) GetNode(context.Context, string) (NodeIdentity, error) { return f.node, nil }

func valid() (PV, PVC, NodeIdentity, Allowlist) {
	n := NodeIdentity{"n", "host", "nodeuid", "provider"}
	p := PV{Name: "pv", Phase: "Bound", VolumeMode: "local", StorageClass: StorageClass, LocalPath: "/mnt/local/kafka/kafka/data", ClaimNamespace: "kafka", ClaimName: "data", ClaimUID: "pvcuid", NodeHostname: "host", NodeOperator: "In", NodeAffinityValid: true}
	c := PVC{"kafka", "data", "pvcuid", "pv", "Bound"}
	return p, c, n, Allowlist{"n": n}
}
func TestCandidatesExactHierarchyAndIdentity(t *testing.T) {
	p, c, n, a := valid()
	f := &fakeReader{pvs: []PV{p}, pv: p, pvc: c, node: n}
	got, err := Candidates(context.Background(), f, a, "n")
	if err != nil || len(got) != 1 {
		t.Fatalf("got %d, %v", len(got), err)
	}
	p.LocalPath = "/mnt/local/kafka/kafka/other"
	f.pvs = []PV{p}
	got, _ = Candidates(context.Background(), f, a, "n")
	if len(got) != 0 {
		t.Fatal("accepted wrong path")
	}
	p, c, n, a = valid()
	f = &fakeReader{pvs: []PV{p}, pv: p, pvc: c, node: n}
	got, _ = Candidates(context.Background(), f, a, "other")
	if len(got) != 0 {
		t.Fatal("accepted nonlocal node")
	}
}
func TestVerifyIdentity(t *testing.T) {
	_, _, n, a := valid()
	if VerifyIdentity(a, n) != nil {
		t.Fatal("valid identity rejected")
	}
	n.ProviderID = "other"
	if VerifyIdentity(a, n) == nil {
		t.Fatal("changed provider accepted")
	}
}
func TestMountOptionsAndParsing(t *testing.T) {
	d := t.TempDir()
	f := filepath.Join(d, "mountinfo")
	line := "1 0 8:1 / /mnt/local rw,nosuid - ext4 /dev/nvme0n1 rw,noatime\n"
	if err := os.WriteFile(f, []byte(line), 0600); err != nil {
		t.Fatal(err)
	}
	if err := VerifyHostMount(f, MountSignature{"/dev/nvme0n1", "ext4", []string{"noatime", "nosuid"}}); err != nil {
		t.Fatal(err)
	}
	if VerifyHostMount(f, MountSignature{"/dev/nvme0n1", "ext4", []string{"ro"}}) == nil {
		t.Fatal("bad options accepted")
	}
	if err := os.WriteFile(f, []byte("1 0 8:1 / /mnt/local ro - ext4 /dev/nvme0n1 rw\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if VerifyHostMount(f, MountSignature{"/dev/nvme0n1", "ext4", []string{}}) == nil {
		t.Fatal("raw read-only mount accepted")
	}
}

func TestCandidateRejectsAmbiguousAffinity(t *testing.T) {
	p, c, n, a := valid()
	p.NodeAffinityValid = false
	f := &fakeReader{pvs: []PV{p}, pv: p, pvc: c, node: n}
	got, err := Candidates(context.Background(), f, a, "n")
	if err != nil || len(got) != 0 {
		t.Fatal("ambiguous affinity accepted")
	}
}
func TestEnsureHierarchyRejectsSymlink(t *testing.T) {
	root := t.TempDir()
	if err := os.Symlink("/tmp", filepath.Join(root, "kafka")); err != nil {
		t.Fatal(err)
	}
	if err := ensureHierarchy(root, filepath.Join(root, "kafka", "ns", "claim")); err == nil {
		t.Fatal("symlink hierarchy accepted")
	}
}
func TestEngineRevalidates(t *testing.T) {
	p, c, n, a := valid()
	f := &fakeReader{pvs: []PV{p}, pv: p, pvc: c, node: n, change: true}
	d := t.TempDir()
	m := filepath.Join(d, "mountinfo")
	if err := os.WriteFile(m, []byte("1 0 8:1 / /mnt/local rw - ext4 /dev/nvme rw\n"), 0600); err != nil {
		t.Fatal(err)
	}
	e := Engine{Reader: f, Allowlist: a, MountInfo: m, Mount: MountSignature{"/dev/nvme", "ext4", []string{"rw"}}}
	if e.Repair(context.Background()) == nil {
		t.Fatal("changed resource accepted")
	}
}

func TestLoadConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(path, []byte(`{"mountFilesystem":"ext4","mountSource":"/dev/nvme","mountOptions":["nodev"],"nodes":[{"name":"n","hostname":"host","uid":"nodeuid","providerID":"provider"}]}`), 0600); err != nil {
		t.Fatal(err)
	}
	config, err := LoadConfig(path)
	if err != nil || config.Nodes[0].Name != "n" {
		t.Fatalf("config: %#v, %v", config, err)
	}
}
