//go:build linux

package main

import (
	"context"
	"log"
	"os"
	"time"

	"github.com/coreweave/reference-architecture/kafka-local-nvme/internal/repair"
)

func main() {
	config, err := repair.LoadConfig(env("REPAIR_CONFIG_PATH", "/etc/repair/config.json"))
	if err != nil {
		log.Fatalf("invalid repair config: %v", err)
	}
	reader, err := repair.NewInClusterReader()
	if err != nil {
		log.Fatalf("Kubernetes API initialization failed: %v", err)
	}
	allowed := repair.Allowlist{}
	for _, node := range config.Nodes {
		allowed[node.Name] = node
	}
	engine := &repair.Engine{Reader: reader, Allowlist: allowed, NodeName: os.Getenv("NODE_NAME"), MountInfo: "/proc/1/mountinfo", Mount: repair.MountSignature{Source: config.MountSource, FSType: config.MountFilesystem, Options: config.MountOptions}}
	for {
		if err := engine.Repair(context.Background()); err != nil {
			log.Printf("repair reconciliation refused: %v", err)
		}
		time.Sleep(30 * time.Second)
	}
}
func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
