# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.20.2",
# ]
# ///

import marimo

__generated_with = "0.20.3"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import os
    import subprocess

    import marimo as mo
    from lib.ui import about, banner, security_disclaimer, table_of_contents

    LAB_NAMESPACE = "arena-k8s-lab"
    LAB_LABEL_KEY = "app.kubernetes.io/part-of"
    LAB_LABEL_VALUE = "arena-k8s-lab"

    CONFIGMAP_NAME = "arena-k8s-config"
    DEPLOYMENT_NAME = "arena-k8s-web"
    SERVICE_NAME = "arena-k8s-web"
    JOB_NAME = "arena-k8s-job"

    SERVICE_ACCOUNT_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    SERVICE_ACCOUNT_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    KUBECTL_KUBECONFIG_PATH = "/tmp/arena-incluster-kubectl.yaml"


    def truncate(text: str, max_chars: int = 4000) -> str:
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}\n...output truncated..."


    def run_command(command: str, timeout_seconds: int = 180) -> dict:
        """Run a shell command and return structured result."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
            return {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "ok": result.returncode == 0,
            }
        except subprocess.TimeoutExpired as err:
            stdout = str(err.stdout or "").strip() if err.stdout else ""
            stderr = str(err.stderr or "").strip() if err.stderr else ""
            return {
                "command": command,
                "returncode": 124,
                "stdout": stdout,
                "stderr": f"Command timed out after {timeout_seconds}s. {stderr}".strip(),
                "ok": False,
            }


    @mo.cache
    def execute_step(command: str) -> dict:
        """Cached wrapper so re-renders don't re-execute commands."""
        return run_command(command)


    def configure_incluster_kubectl(kubeconfig_path: str) -> tuple[bool, str]:
        """Create a kubeconfig from mounted service-account credentials."""
        host = os.getenv("KUBERNETES_SERVICE_HOST", "")
        port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "") or os.getenv("KUBERNETES_SERVICE_PORT", "443")

        if not host:
            return False, "KUBERNETES_SERVICE_HOST is not set."
        if not os.path.exists(SERVICE_ACCOUNT_TOKEN_PATH):
            return False, f"Service account token not found at {SERVICE_ACCOUNT_TOKEN_PATH}."
        if not os.path.exists(SERVICE_ACCOUNT_CA_PATH):
            return False, f"Service account CA cert not found at {SERVICE_ACCOUNT_CA_PATH}."

        with open(SERVICE_ACCOUNT_TOKEN_PATH, "r", encoding="utf-8") as file:
            token = file.read().strip()

        if not token:
            return False, "Service account token file is empty."

        kubeconfig = f"""
apiVersion: v1
kind: Config
clusters:
- name: in-cluster
  cluster:
    server: https://{host}:{port}
    certificate-authority: {SERVICE_ACCOUNT_CA_PATH}
users:
- name: service-account
  user:
    token: {token}
contexts:
- name: in-cluster
  context:
    cluster: in-cluster
    user: service-account
current-context: in-cluster
"""
        with open(kubeconfig_path, "w", encoding="utf-8") as file:
            file.write(kubeconfig.strip() + "\n")

        os.chmod(kubeconfig_path, 0o600)
        os.environ["KUBECONFIG"] = kubeconfig_path
        return True, kubeconfig_path


    def ensure_kubectl_access() -> tuple[bool, str]:
        """Configure kubectl for either in-cluster or local current-context usage."""
        kubectl_check = run_command("kubectl version --client")
        if not bool(kubectl_check["ok"]):
            return (
                False,
                "`kubectl` is not available. Install it in this environment and rerun all cells.",
            )

        incluster_ok, incluster_message = configure_incluster_kubectl(KUBECTL_KUBECONFIG_PATH)
        if incluster_ok:
            current_context = run_command("kubectl config current-context")
            if bool(current_context["ok"]):
                return (
                    True,
                    f"Using in-cluster service account context `{current_context['stdout']}` via `{KUBECTL_KUBECONFIG_PATH}`.",
                )
            return (
                True,
                f"Using in-cluster service account credentials via `{KUBECTL_KUBECONFIG_PATH}`.",
            )

        current_context = run_command("kubectl config current-context")
        if bool(current_context["ok"]):
            return True, f"Using local kubectl context `{current_context['stdout']}`."

        details = str(current_context["stderr"]) if current_context["stderr"] else incluster_message
        return (
            False,
            "kubectl is installed but no cluster context is usable. "
            "If running locally, set a context with `kubectl config use-context <name>`. "
            f"Details: `{details}`",
        )


    def step_cell(title: str, cmd: str, btn, clicked: bool) -> mo.Html:
        """Render a single step: title + button, command, and result if clicked."""
        _output = None
        if clicked:
            _r = execute_step(cmd)
            _status = "SUCCESS" if _r["ok"] else "FAILED"
            _stdout = truncate(str(_r["stdout"])) if _r["stdout"] else "(no output)"
            _stderr_block = ""
            if _r["stderr"] and not _r["ok"]:
                _stderr_block = f"\n**stderr:**\n```\n{truncate(str(_r['stderr']))}\n```"
            _output = mo.md(f"`{_status}`\n```\n{_stdout}\n```{_stderr_block}")
        return mo.vstack([
            mo.hstack([mo.md(f"**{title}**"), btn], justify="space-between", align="center"),
            mo.md(f"```\n{cmd}\n```"),
            _output,
        ])


    RUN_BUTTON = dict(value=0, on_click=lambda v: v + 1, label="Run")


# ============================================================
# Header
# ============================================================


@app.cell(hide_code=True)
def _():
    mo.vstack([
        banner(),
        about(
            "Kubernetes",
            """This notebook is a hands-on introduction to Kubernetes on CoreWeave Kubernetes Service (CKS).<br>
               Work through each section in order, clicking **Run** on each step to execute commands one at a time.<br>
               _If you are running this notebook in edit mode, start by running all cells in the bottom right._
            """,
        ),
        table_of_contents([
            {"title": "Cluster Access", "description": "Verify kubectl connectivity."},
            {"title": "Environment and Namespace Setup", "description": "Create the lab namespace."},
            {"title": "ConfigMap CRUD Lab", "description": "Create, read, update, and delete a ConfigMap."},
            {"title": "Deployment CRUD Lab", "description": "Deploy, scale, and update a workload."},
            {"title": "Service CRUD Lab", "description": "Expose a deployment and manage services."},
            {"title": "Job CRUD Lab", "description": "Run a batch job and inspect logs."},
            {"title": "Cleanup", "description": "Delete lab resources and namespace."},
        ]),
        security_disclaimer(),
    ])
    return


@app.cell(hide_code=True)
def _():
    kubectl_ready, access_message = ensure_kubectl_access()
    mo.md(f"""
---
## Cluster Access

**kubectl status:** `{"READY" if kubectl_ready else "NOT READY"}`

{access_message}
""")
    return (kubectl_ready,)


# ============================================================
# Environment and Namespace Setup
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Environment and Namespace Setup\n\nCreate and verify the dedicated lab namespace.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    env_b1 = mo.ui.button(**RUN_BUTTON)
    env_b2 = mo.ui.button(**RUN_BUTTON)
    env_b3 = mo.ui.button(**RUN_BUTTON)
    env_b4 = mo.ui.button(**RUN_BUTTON)
    env_b5 = mo.ui.button(**RUN_BUTTON)
    return env_b1, env_b2, env_b3, env_b4, env_b5


@app.cell(hide_code=True)
def _(env_b1):
    step_cell("1. Check API Server", "kubectl cluster-info", env_b1, env_b1.value > 0)
    return


@app.cell(hide_code=True)
def _(env_b2):
    step_cell("2. List Namespaces", "kubectl get namespace", env_b2, env_b2.value > 0)
    return


@app.cell(hide_code=True)
def _(env_b3):
    step_cell(
        "3. Create Lab Namespace",
        f"kubectl create namespace {LAB_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -",
        env_b3, env_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(env_b4):
    step_cell(
        "4. Label Lab Namespace",
        f"kubectl label namespace {LAB_NAMESPACE} {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --overwrite",
        env_b4, env_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(env_b5):
    step_cell(
        "5. Verify Namespace Labels",
        f"kubectl get namespace {LAB_NAMESPACE} --show-labels",
        env_b5, env_b5.value > 0,
    )
    return


# ============================================================
# ConfigMap CRUD Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## ConfigMap CRUD Lab\n\nCreate, read, update, and delete a ConfigMap.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    cm_b1 = mo.ui.button(**RUN_BUTTON)
    cm_b2 = mo.ui.button(**RUN_BUTTON)
    cm_b3 = mo.ui.button(**RUN_BUTTON)
    cm_b4 = mo.ui.button(**RUN_BUTTON)
    cm_b5 = mo.ui.button(**RUN_BUTTON)
    cm_b6 = mo.ui.button(**RUN_BUTTON)
    return cm_b1, cm_b2, cm_b3, cm_b4, cm_b5, cm_b6


@app.cell(hide_code=True)
def _(cm_b1):
    step_cell(
        "1. Create ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} create configmap {CONFIGMAP_NAME} --from-literal=MODE=learning --from-literal=OWNER=arena --dry-run=client -o yaml | kubectl apply -f -",
        cm_b1, cm_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b2):
    step_cell(
        "2. Label ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} label configmap {CONFIGMAP_NAME} {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --overwrite",
        cm_b2, cm_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b3):
    step_cell(
        "3. Read ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} get configmap {CONFIGMAP_NAME} -o yaml",
        cm_b3, cm_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b4):
    step_cell(
        "4. Patch ConfigMap Data",
        f"""kubectl -n {LAB_NAMESPACE} patch configmap {CONFIGMAP_NAME} --type merge -p '{{"data":{{"MODE":"advanced","TOPIC":"crud"}}}}'""",
        cm_b4, cm_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b5):
    step_cell(
        "5. Verify Updated ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} get configmap {CONFIGMAP_NAME} -o yaml",
        cm_b5, cm_b5.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b6):
    step_cell(
        "6. Delete ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} delete configmap {CONFIGMAP_NAME} --ignore-not-found=true",
        cm_b6, cm_b6.value > 0,
    )
    return


# ============================================================
# Deployment CRUD Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Deployment CRUD Lab\n\nDeploy, scale, and update a workload.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    dep_b1 = mo.ui.button(**RUN_BUTTON)
    dep_b2 = mo.ui.button(**RUN_BUTTON)
    dep_b3 = mo.ui.button(**RUN_BUTTON)
    dep_b4 = mo.ui.button(**RUN_BUTTON)
    dep_b5 = mo.ui.button(**RUN_BUTTON)
    dep_b6 = mo.ui.button(**RUN_BUTTON)
    dep_b7 = mo.ui.button(**RUN_BUTTON)
    dep_b8 = mo.ui.button(**RUN_BUTTON)
    return dep_b1, dep_b2, dep_b3, dep_b4, dep_b5, dep_b6, dep_b7, dep_b8


@app.cell(hide_code=True)
def _(dep_b1):
    step_cell(
        "1. Create Deployment",
        f"kubectl -n {LAB_NAMESPACE} create deployment {DEPLOYMENT_NAME} --image=nginx:1.27 --replicas=1 --dry-run=client -o yaml | kubectl apply -f -",
        dep_b1, dep_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b2):
    step_cell(
        "2. Label Deployment",
        f"kubectl -n {LAB_NAMESPACE} label deployment {DEPLOYMENT_NAME} {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --overwrite",
        dep_b2, dep_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b3):
    step_cell(
        "3. Scale Deployment",
        f"kubectl -n {LAB_NAMESPACE} scale deployment {DEPLOYMENT_NAME} --replicas=2",
        dep_b3, dep_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b4):
    step_cell(
        "4. Wait for Rollout",
        f"kubectl -n {LAB_NAMESPACE} rollout status deployment/{DEPLOYMENT_NAME} --timeout=120s",
        dep_b4, dep_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b5):
    step_cell(
        "5. Update Deployment Image",
        f"kubectl -n {LAB_NAMESPACE} set image deployment/{DEPLOYMENT_NAME} *=nginx:1.27.5",
        dep_b5, dep_b5.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b6):
    step_cell(
        "6. Wait for Updated Rollout",
        f"kubectl -n {LAB_NAMESPACE} rollout status deployment/{DEPLOYMENT_NAME} --timeout=120s",
        dep_b6, dep_b6.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b7):
    step_cell(
        "7. Read Deployment",
        f"kubectl -n {LAB_NAMESPACE} get deployment {DEPLOYMENT_NAME}",
        dep_b7, dep_b7.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b8):
    step_cell(
        "8. Read Deployment Pods",
        f"kubectl -n {LAB_NAMESPACE} get pods -l app={DEPLOYMENT_NAME}",
        dep_b8, dep_b8.value > 0,
    )
    return


# ============================================================
# Service CRUD Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Service CRUD Lab\n\nExpose a deployment and update service behavior.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    svc_b1 = mo.ui.button(**RUN_BUTTON)
    svc_b2 = mo.ui.button(**RUN_BUTTON)
    svc_b3 = mo.ui.button(**RUN_BUTTON)
    svc_b4 = mo.ui.button(**RUN_BUTTON)
    svc_b5 = mo.ui.button(**RUN_BUTTON)
    svc_b6 = mo.ui.button(**RUN_BUTTON)
    return svc_b1, svc_b2, svc_b3, svc_b4, svc_b5, svc_b6


@app.cell(hide_code=True)
def _(svc_b1):
    step_cell(
        "1. Expose Deployment as Service",
        f"kubectl -n {LAB_NAMESPACE} expose deployment {DEPLOYMENT_NAME} --name={SERVICE_NAME} --port=80 --target-port=80 --type=ClusterIP --dry-run=client -o yaml | kubectl apply -f -",
        svc_b1, svc_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b2):
    step_cell(
        "2. Label Service",
        f"kubectl -n {LAB_NAMESPACE} label service {SERVICE_NAME} {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --overwrite",
        svc_b2, svc_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b3):
    step_cell(
        "3. Read Service",
        f"kubectl -n {LAB_NAMESPACE} get service {SERVICE_NAME} -o wide",
        svc_b3, svc_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b4):
    step_cell(
        "4. Read Endpoints",
        f"kubectl -n {LAB_NAMESPACE} get endpoints {SERVICE_NAME}",
        svc_b4, svc_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b5):
    step_cell(
        "5. Patch Service Session Affinity",
        f"""kubectl -n {LAB_NAMESPACE} patch service {SERVICE_NAME} --type merge -p '{{"spec":{{"sessionAffinity":"ClientIP"}}}}'""",
        svc_b5, svc_b5.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b6):
    step_cell(
        "6. Read Service YAML",
        f"kubectl -n {LAB_NAMESPACE} get service {SERVICE_NAME} -o yaml",
        svc_b6, svc_b6.value > 0,
    )
    return


# ============================================================
# Job CRUD Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Job CRUD Lab\n\nRun a batch job and inspect logs.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    job_b1 = mo.ui.button(**RUN_BUTTON)
    job_b2 = mo.ui.button(**RUN_BUTTON)
    job_b3 = mo.ui.button(**RUN_BUTTON)
    job_b4 = mo.ui.button(**RUN_BUTTON)
    job_b5 = mo.ui.button(**RUN_BUTTON)
    return job_b1, job_b2, job_b3, job_b4, job_b5


@app.cell(hide_code=True)
def _(job_b1):
    step_cell(
        "1. Delete Old Job (if any)",
        f"kubectl -n {LAB_NAMESPACE} delete job {JOB_NAME} --ignore-not-found=true",
        job_b1, job_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(job_b2):
    step_cell(
        "2. Create Job",
        f"kubectl -n {LAB_NAMESPACE} create job {JOB_NAME} --image=busybox:1.36 -- /bin/sh -c 'echo hello-from-cks; sleep 3; echo completed'",
        job_b2, job_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(job_b3):
    step_cell(
        "3. Label Job",
        f"kubectl -n {LAB_NAMESPACE} label job {JOB_NAME} {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --overwrite",
        job_b3, job_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(job_b4):
    step_cell(
        "4. Wait for Completion",
        f"kubectl -n {LAB_NAMESPACE} wait --for=condition=complete --timeout=120s job/{JOB_NAME}",
        job_b4, job_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(job_b5):
    step_cell(
        "5. Read Job Logs",
        f"kubectl -n {LAB_NAMESPACE} logs job/{JOB_NAME}",
        job_b5, job_b5.value > 0,
    )
    return


# ============================================================
# Cleanup
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Cleanup\n\nDelete labeled resources and the lab namespace.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    cln_b1 = mo.ui.button(**RUN_BUTTON)
    cln_b2 = mo.ui.button(**RUN_BUTTON)
    cln_b3 = mo.ui.button(**RUN_BUTTON)
    cln_b4 = mo.ui.button(**RUN_BUTTON)
    return cln_b1, cln_b2, cln_b3, cln_b4


@app.cell(hide_code=True)
def _(cln_b1):
    step_cell(
        "1. Delete Labeled Resources",
        f"kubectl -n {LAB_NAMESPACE} delete all,configmap,job -l {LAB_LABEL_KEY}={LAB_LABEL_VALUE} --ignore-not-found=true || true",
        cln_b1, cln_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cln_b2):
    step_cell(
        "2. List Remaining Namespace Resources",
        f"kubectl -n {LAB_NAMESPACE} get all || true",
        cln_b2, cln_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cln_b3):
    step_cell(
        "3. Delete Lab Namespace",
        f"kubectl delete namespace {LAB_NAMESPACE} --ignore-not-found=true",
        cln_b3, cln_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cln_b4):
    step_cell(
        "4. Verify Namespace Removal",
        f"kubectl get namespace {LAB_NAMESPACE} || true",
        cln_b4, cln_b4.value > 0,
    )
    return


if __name__ == "__main__":
    app.run()
