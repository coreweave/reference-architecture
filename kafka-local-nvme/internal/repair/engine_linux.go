//go:build linux

package repair

import (
	"context"
	"fmt"
	"sync"
)

type Engine struct {
	Reader    Reader
	Allowlist Allowlist
	NodeName  string
	MountInfo string
	Mount     MountSignature
	ready     bool
	mu        sync.RWMutex
}

func (e *Engine) Ready() bool { e.mu.RLock(); defer e.mu.RUnlock(); return e.ready }
func (e *Engine) Repair(ctx context.Context) error {
	e.mu.Lock()
	e.ready = false
	e.mu.Unlock()
	candidates, err := Candidates(ctx, e.Reader, e.Allowlist, e.NodeName)
	if err != nil {
		return err
	}
	if err = VerifyHostMount(e.MountInfo, e.Mount); err != nil {
		return err
	}
	for _, candidate := range candidates {
		pv, err := e.Reader.GetPV(ctx, candidate.PV.Name)
		if err != nil {
			return err
		}
		pvc, err := e.Reader.GetPVC(ctx, candidate.PVC.Namespace, candidate.PVC.Name)
		if err != nil {
			return err
		}
		node, err := e.Reader.GetNode(ctx, candidate.Node.Name)
		if err != nil {
			return err
		}
		expected, _ := ExpectedPath(pv.ClaimNamespace, pv.ClaimName)
		if pv != candidate.PV || pvc != candidate.PVC || node != candidate.Node || node.Name != e.NodeName || pv.LocalPath != expected || VerifyIdentity(e.Allowlist, node) != nil {
			return fmt.Errorf("candidate %s changed before mutation", candidate.PV.Name)
		}
		if err = VerifyHostMount(e.MountInfo, e.Mount); err != nil {
			return err
		}
		if err = EnsureHierarchy(expected); err != nil {
			return err
		}
	}
	e.mu.Lock()
	e.ready = true
	e.mu.Unlock()
	return nil
}
