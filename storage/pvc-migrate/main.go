package main

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
	"time"
)

type cluster struct {
	ctx, kubeconfig, ns string
}

func (c cluster) kubectl(args ...string) *exec.Cmd {
	var cmdArgs []string
	if c.kubeconfig != "" {
		cmdArgs = append(cmdArgs, "--kubeconfig", c.kubeconfig)
	}
	if c.ctx != "" {
		cmdArgs = append(cmdArgs, "--context", c.ctx)
	}
	cmdArgs = append(cmdArgs, args...)
	return exec.Command("kubectl", cmdArgs...)
}

func (c cluster) run(stdin string, args ...string) {
	cmd := c.kubectl(args...)
	cmd.Args = append(cmd.Args, "-n", c.ns)
	fmt.Printf("Running: %s\n", strings.Join(cmd.Args, " "))
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if stdin != "" {
		cmd.Stdin = strings.NewReader(stdin)
	}
	if err := cmd.Run(); err != nil {
		log.Fatalf("kubectl failed: %v", err)
	}
}

func (c cluster) output(args ...string) string {
	cmd := c.kubectl(args...)
	cmd.Args = append(cmd.Args, "-n", c.ns)
	var out, errOut bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errOut
	if err := cmd.Run(); err != nil {
		fmt.Printf("STDERR: %s\n", errOut.String())
		return ""
	}
	return strings.TrimSpace(out.String())
}

func (c cluster) apply(yaml string) { c.run(yaml, "apply", "-f", "-") }
func (c cluster) wait(resource string) {
	c.run("", "wait", "--for=condition=complete", resource, "--timeout=-1s")
}
func (c cluster) delete(resource string) {
	c.run("", "delete", resource, "--ignore-not-found", "--wait=false")
}

func main() {
	pvc := flag.String("pvc", "", "PVC name (used for both source and target)")
	srcNS := flag.String("src-ns", "", "Source namespace")
	tgtNS := flag.String("tgt-ns", "", "Target namespace")
	srcCtx := flag.String("src-ctx", "", "Source cluster context")
	tgtCtx := flag.String("tgt-ctx", "", "Target cluster context")
	srcKubeconfig := flag.String("src-kubeconfig", "", "Source cluster kubeconfig path")
	tgtKubeconfig := flag.String("tgt-kubeconfig", "", "Target cluster kubeconfig path")
	flag.Parse()

	if *pvc == "" || *srcNS == "" || *tgtNS == "" {
		flag.Usage()
		os.Exit(1)
	}

	src := cluster{*srcCtx, *srcKubeconfig, *srcNS}
	tgt := cluster{*tgtCtx, *tgtKubeconfig, *tgtNS}

	fmt.Println("\nStep 1: Find or create RClone password")
	pass := getExistingPassword(src)
	if pass == "" {
		pass = genPassword(16)
		fmt.Println("Generated new password")
	} else {
		fmt.Println("Found existing password")
	}

	fmt.Println("\nStep 2: Deploy rclone server (source)")
	src.apply(readFile("yaml/cert.yaml"))
	src.apply(substitute(readFile("yaml/server.yaml"),
		"$PVC_NAME", *pvc,
		"$RCLONE_PASS", pass,
	))

	fmt.Println("\nStep 3: Detect rclone server endpoint")
	h := waitForLB(src)
	fmt.Printf("Using host: %s\n", h)

	obscured := obscurePassword(pass)

	fmt.Println("\nStep 4: Deploy rclone client (target)")
	tgt.delete("job/rclone-client")
	tgt.apply(substitute(readFile("yaml/client.yaml"),
		"$PVC_NAME", *pvc,
		"$RCLONE_SERVER_HOST", h,
		"$RCLONE_OBSCURED_PASS", obscured,
	))

	fmt.Println("\nMigration job submitted. Monitor in-cluster")
}

func readFile(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("failed to read %s: %v", path, err)
	}
	return string(b)
}

func substitute(s string, pairs ...string) string {
	r := strings.NewReplacer(pairs...)
	return r.Replace(s)
}

func waitForLB(c cluster) string {
	for range 30 {
		ip := c.output("get", "svc", "rclone-server", "-o", `jsonpath={.status.loadBalancer.ingress[0].ip}`)
		if ip != "" {
			return ip
		}
		host := c.output("get", "svc", "rclone-server", "-o", `jsonpath={.status.loadBalancer.ingress[0].hostname}`)
		if host != "" {
			return host
		}
		time.Sleep(5 * time.Second)
	}
	log.Fatal("timed out waiting for LoadBalancer endpoint")
	return ""
}

func getExistingPassword(c cluster) string {
	encoded := c.output("get", "secret", "rclone-server-secret", "-o", "jsonpath={.data.PASS}")
	if encoded == "" {
		return ""
	}
	b, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return ""
	}
	return string(b)
}

func obscurePassword(pass string) string {
	cmd := exec.Command("rclone", "obscure", pass)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		log.Fatalf("rclone obscure failed: %v", err)
	}
	return strings.TrimSpace(out.String())
}

func genPassword(length int) string {
	b := make([]byte, length)
	if _, err := rand.Read(b); err != nil {
		log.Fatalf("failed to generate password: %v", err)
	}
	return hex.EncodeToString(b)
}
