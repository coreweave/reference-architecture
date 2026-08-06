package repair

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
)

var ErrUnavailable = errors.New("Kubernetes reader is not configured")

// UnavailableReader prevents accidental mutation-capable fallback behaviour.
type UnavailableReader struct{}

func (UnavailableReader) ListPVs(context.Context) ([]PV, error)     { return nil, ErrUnavailable }
func (UnavailableReader) GetPV(context.Context, string) (PV, error) { return PV{}, ErrUnavailable }
func (UnavailableReader) GetPVC(context.Context, string, string) (PVC, error) {
	return PVC{}, ErrUnavailable
}
func (UnavailableReader) GetNode(context.Context, string) (NodeIdentity, error) {
	return NodeIdentity{}, ErrUnavailable
}

type APIReader struct {
	client      *http.Client
	base, token string
}

func NewInClusterReader() (*APIReader, error) {
	token, err := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/token")
	if err != nil {
		return nil, err
	}
	ca, err := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(ca) {
		return nil, errors.New("invalid service account CA")
	}
	host, port := os.Getenv("KUBERNETES_SERVICE_HOST"), os.Getenv("KUBERNETES_SERVICE_PORT")
	if host == "" || port == "" {
		return nil, ErrUnavailable
	}
	return &APIReader{&http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}}}, "https://" + host + ":" + port, string(token)}, nil
}
func (r *APIReader) get(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, r.base+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+r.token)
	res, err := r.client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return fmt.Errorf("Kubernetes GET %s: %s", path, res.Status)
	}
	return json.NewDecoder(res.Body).Decode(out)
}

type object struct {
	Metadata struct {
		Name      string `json:"name"`
		Namespace string `json:"namespace"`
		UID       string `json:"uid"`
	} `json:"metadata"`
	Status struct {
		Phase string `json:"phase"`
	} `json:"status"`
	Spec struct {
		StorageClassName string `json:"storageClassName"`
		ClaimRef         *struct {
			Namespace string `json:"namespace"`
			Name      string `json:"name"`
			UID       string `json:"uid"`
		} `json:"claimRef"`
		Local *struct {
			Path string `json:"path"`
		} `json:"local"`
		NodeAffinity *struct {
			Required struct {
				NodeSelectorTerms []struct {
					MatchExpressions []struct {
						Key      string   `json:"key"`
						Operator string   `json:"operator"`
						Values   []string `json:"values"`
					} `json:"matchExpressions"`
				} `json:"nodeSelectorTerms"`
			} `json:"required"`
		} `json:"nodeAffinity"`
		VolumeName string `json:"volumeName"`
	} `json:"spec"`
}

func pv(o object) PV {
	p := PV{Name: o.Metadata.Name, Phase: o.Status.Phase, VolumeMode: "local", StorageClass: o.Spec.StorageClassName}
	if o.Spec.ClaimRef != nil {
		p.ClaimNamespace = o.Spec.ClaimRef.Namespace
		p.ClaimName = o.Spec.ClaimRef.Name
		p.ClaimUID = o.Spec.ClaimRef.UID
	}
	if o.Spec.Local != nil {
		p.LocalPath = o.Spec.Local.Path
	}
	if o.Spec.NodeAffinity != nil && len(o.Spec.NodeAffinity.Required.NodeSelectorTerms) == 1 && len(o.Spec.NodeAffinity.Required.NodeSelectorTerms[0].MatchExpressions) == 1 {
		e := o.Spec.NodeAffinity.Required.NodeSelectorTerms[0].MatchExpressions[0]
		if e.Key == "kubernetes.io/hostname" && e.Operator == "In" && len(e.Values) == 1 {
			p.NodeHostname = e.Values[0]
			p.NodeOperator = e.Operator
			p.NodeAffinityValid = true
		}
	}
	return p
}
func (r *APIReader) ListPVs(c context.Context) ([]PV, error) {
	var x struct {
		Items []object `json:"items"`
	}
	if err := r.get(c, "/api/v1/persistentvolumes", &x); err != nil {
		return nil, err
	}
	out := make([]PV, 0, len(x.Items))
	for _, o := range x.Items {
		out = append(out, pv(o))
	}
	return out, nil
}
func (r *APIReader) GetPV(c context.Context, n string) (PV, error) {
	var x object
	err := r.get(c, "/api/v1/persistentvolumes/"+url.PathEscape(n), &x)
	return pv(x), err
}
func (r *APIReader) GetPVC(c context.Context, ns, n string) (PVC, error) {
	var x object
	err := r.get(c, "/api/v1/namespaces/"+url.PathEscape(ns)+"/persistentvolumeclaims/"+url.PathEscape(n), &x)
	return PVC{Namespace: x.Metadata.Namespace, Name: x.Metadata.Name, UID: x.Metadata.UID, VolumeName: x.Spec.VolumeName, Phase: x.Status.Phase}, err
}
func (r *APIReader) GetNode(c context.Context, n string) (NodeIdentity, error) {
	var x struct {
		Metadata struct {
			Name   string            `json:"name"`
			UID    string            `json:"uid"`
			Labels map[string]string `json:"labels"`
		} `json:"metadata"`
		Spec struct {
			ProviderID string `json:"providerID"`
		} `json:"spec"`
	}
	err := r.get(c, "/api/v1/nodes/"+url.PathEscape(n), &x)
	return NodeIdentity{Name: x.Metadata.Name, Hostname: x.Metadata.Labels["kubernetes.io/hostname"], UID: x.Metadata.UID, ProviderID: x.Spec.ProviderID}, err
}
func LoadConfig(path string) (Config, error) {
	b, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return Config{}, err
	}
	var c Config
	if err = json.Unmarshal(b, &c); err != nil {
		return Config{}, err
	}
	if c.MountFilesystem == "" || c.MountSource == "" || len(c.MountOptions) == 0 || len(c.Nodes) == 0 {
		return Config{}, errors.New("incomplete repair config")
	}
	return c, nil
}
