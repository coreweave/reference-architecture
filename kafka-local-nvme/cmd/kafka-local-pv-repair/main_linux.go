//go:build linux

package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/coreweave/reference-architecture/kafka-local-nvme/internal/repair"
)

func main() {
	config, err := repair.LoadConfig(env("REPAIR_CONFIG_PATH", "/etc/repair/config.json"))
	if err != nil {
		log.Printf("invalid repair config: %v", err)
		serve(nil)
		return
	}
	reader, err := repair.NewInClusterReader()
	if err != nil {
		log.Printf("Kubernetes API unavailable: %v", err)
		serve(nil)
		return
	}
	allowed := repair.Allowlist{}
	for _, node := range config.Nodes {
		allowed[node.Name] = node
	}
	engine := &repair.Engine{Reader: reader, Allowlist: allowed, NodeName: os.Getenv("NODE_NAME"), MountInfo: "/proc/1/mountinfo", Mount: repair.MountSignature{Source: config.MountSource, FSType: config.MountFilesystem, Options: config.MountOptions}}
	go func() {
		for {
			if err := engine.Repair(context.Background()); err != nil {
				log.Printf("repair reconciliation refused: %v", err)
			}
			time.Sleep(30 * time.Second)
		}
	}()
	serve(engine)
}

func serve(engine *repair.Engine) {
	var once sync.Once
	http.HandleFunc("/livez", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	http.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if engine == nil || !engine.Ready() {
			http.Error(w, "safe reconciliation has not completed", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	once.Do(func() {
		if err := http.ListenAndServe(":"+env("PORT", "8080"), nil); err != nil {
			log.Fatal(err)
		}
	})
}
func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
