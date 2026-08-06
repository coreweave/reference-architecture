package repair

import "context"

const (
	StorageClass = "kafka-local"
	HostRoot     = "/mnt/local"
)

type PV struct {
	Name, Phase, VolumeMode, StorageClass, LocalPath, ClaimNamespace, ClaimName, ClaimUID, NodeHostname, NodeOperator string
	NodeAffinityValid                                                                                                 bool
}

type PVC struct{ Namespace, Name, UID, VolumeName, Phase string }
type NodeIdentity struct{ Name, Hostname, UID, ProviderID string }

// Reader is deliberately read-only. Implementations must never mutate Kubernetes state.
type Reader interface {
	ListPVs(context.Context) ([]PV, error)
	GetPV(context.Context, string) (PV, error)
	GetPVC(context.Context, string, string) (PVC, error)
	GetNode(context.Context, string) (NodeIdentity, error)
}

type Allowlist map[string]NodeIdentity // keyed by node name
type Config struct {
	MountFilesystem, MountSource string
	MountOptions                 []string
	Nodes                        []NodeIdentity
}
type Candidate struct {
	PV   PV
	PVC  PVC
	Node NodeIdentity
}
type MountSignature struct {
	Source, FSType string
	Options        []string
}
