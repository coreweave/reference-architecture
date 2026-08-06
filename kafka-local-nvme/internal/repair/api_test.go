package repair

import (
	"context"
	"crypto/x509"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func replaceToken(t *testing.T, path, contents string) {
	t.Helper()
	staged := filepath.Join(filepath.Dir(path), "staged-token")
	if err := os.WriteFile(staged, []byte(contents), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(staged, path); err != nil {
		t.Fatal(err)
	}
}

func TestAPIReaderReloadsAndValidatesToken(t *testing.T) {
	const firstToken = "first-secret-token"
	const secondToken = "second-secret-token"
	tokenPath := filepath.Join(t.TempDir(), "token")
	replaceToken(t, tokenPath, firstToken)

	var headers []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		headers = append(headers, r.Header.Get("Authorization"))
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[]}`))
	}))
	defer server.Close()

	r := &APIReader{client: server.Client(), base: server.URL, tokenPath: tokenPath}
	if _, err := r.ListPVs(context.Background()); err != nil {
		t.Fatal(err)
	}
	replaceToken(t, tokenPath, " \n\t"+secondToken+"\r\n")
	if _, err := r.ListPVs(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got, want := headers, []string{"Bearer " + firstToken, "Bearer " + secondToken}; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("Authorization headers = %q, want %q", got, want)
	}

	replaceToken(t, tokenPath, " \n\t ")
	if _, err := r.ListPVs(context.Background()); err == nil {
		t.Fatal("empty token accepted")
	} else if strings.Contains(err.Error(), firstToken) || strings.Contains(err.Error(), secondToken) {
		t.Fatalf("token leaked in error: %v", err)
	}
	if got := len(headers); got != 2 {
		t.Fatalf("requests after empty token = %d, want 2", got)
	}

	backup := filepath.Join(filepath.Dir(tokenPath), "empty-token")
	if err := os.Rename(tokenPath, backup); err != nil {
		t.Fatal(err)
	}
	stagedDirectory := filepath.Join(filepath.Dir(tokenPath), "token-directory")
	if err := os.Mkdir(stagedDirectory, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(stagedDirectory, tokenPath); err != nil {
		t.Fatal(err)
	}
	if _, err := r.ListPVs(context.Background()); err == nil {
		t.Fatal("directory token path accepted")
	} else if strings.Contains(err.Error(), firstToken) || strings.Contains(err.Error(), secondToken) {
		t.Fatalf("token leaked in error: %v", err)
	}
	if got := len(headers); got != 2 {
		t.Fatalf("requests after unreadable token = %d, want 2", got)
	}
}

func TestAPIRequestTimeout(t *testing.T) {
	client := newAPIClient(x509.NewCertPool())
	if client.Timeout != apiRequestTimeout {
		t.Fatalf("client timeout = %v, want %v", client.Timeout, apiRequestTimeout)
	}
}
