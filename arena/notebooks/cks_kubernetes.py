# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "kubernetes==35.0.0",
#     "marimo>=0.23.6",
#     "ruamel-yaml>=0.19.1",
# ]
# ///

import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import os

    import marimo as mo
    from lib.k8s import ensure_kubectl_access
    from lib.remote_execution_helpers import shell
    from lib.ui import about, banner, security_disclaimer, table_of_contents

    MANIFEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cks_kubernetes")

    LAB_NAMESPACE = "arena-k8s-lab"
    LAB_LABEL_KEY = "app.kubernetes.io/part-of"
    LAB_LABEL_VALUE = "arena-k8s-lab"

    CONFIGMAP_NAME = "arena-k8s-config"
    DEPLOYMENT_NAME = "arena-k8s-web"
    SERVICE_NAME = "arena-k8s-web"
    JOB_NAME = "arena-k8s-job"

    def truncate(text: str, max_chars: int = 4000) -> str:
        """Limit command output to a readable size for notebook display."""
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}\n...output truncated..."

    def step_cell(title: str, cmd: str, btn, clicked: bool, explanation: str = "") -> mo.Html:
        """Render an imperative step: optional explanation, title + button, command, and result if clicked."""
        _output = None
        if clicked:
            _r = shell(cmd, quiet=True, timeout=180)
            _status = "SUCCESS" if _r.ok else "FAILED"
            _stdout_text = _r.strip()
            _stdout = truncate(_stdout_text) if _stdout_text else "(no output)"
            _stderr_block = ""
            _stderr_text = _r.stderr.strip()
            if _stderr_text and not _r.ok:
                _stderr_block = f"\n**stderr:**\n```\n{truncate(_stderr_text)}\n```"
            _output = mo.md(f"`{_status}`\n```\n{_stdout}\n```{_stderr_block}")
        parts = [
            mo.hstack([mo.md(f"**{title}**"), btn], justify="space-between", align="center"),
        ]
        if explanation:
            parts.append(mo.md(explanation))
        parts.append(mo.md(f"```\n{cmd}\n```"))
        if _output is not None:
            parts.append(_output)
        return mo.vstack(parts)

    def manifest_step_cell(
        title: str,
        editor,
        namespace: str | None,
        btn,
        clicked: bool,
        explanation: str = "",
    ) -> mo.Html:
        """Render a declarative step: title + button, optional explanation, editable YAML, result on click.

        `editor` is a `mo.ui.code_editor` whose current `.value` is applied to the cluster
        when the Run button has been clicked. Editing the YAML and re-clicking re-applies.
        """
        _output = None
        if clicked:
            ns_flag = f"-n {namespace} " if namespace else ""
            _r = shell(f"kubectl {ns_flag}apply -f -", quiet=True, timeout=180, input=editor.value)
            _status = "SUCCESS" if _r.ok else "FAILED"
            _stdout_text = _r.strip()
            _stdout = truncate(_stdout_text) if _stdout_text else "(no output)"
            _stderr_block = ""
            _stderr_text = _r.stderr.strip()
            if _stderr_text and not _r.ok:
                _stderr_block = f"\n**stderr:**\n```\n{truncate(_stderr_text)}\n```"
            _output = mo.md(f"`{_status}`\n```\n{_stdout}\n```{_stderr_block}")
        ns_label = f"  *(namespace: `{namespace}`)*" if namespace else ""
        parts = [
            mo.hstack(
                [mo.md(f"**{title}**{ns_label}"), btn],
                justify="space-between",
                align="center",
            ),
        ]
        if explanation:
            parts.append(mo.md(explanation))
        parts.append(editor)
        parts.append(mo.md("_Edit the manifest above if you like, then click **Run** to_ `kubectl apply -f -` _it._"))
        if _output is not None:
            parts.append(_output)
        return mo.vstack(parts)

    def load_manifest(filename: str) -> str:
        """Load a YAML manifest from the `cks_kubernetes/` directory next to this notebook."""
        with open(os.path.join(MANIFEST_DIR, filename), "r", encoding="utf-8") as file:
            return file.read()

    RUN_BUTTON = {"value": 0, "on_click": lambda v: v + 1, "label": "Run"}

    # ----------------------------------------------------------------
    # Manifests (the source of truth for each lab object).
    # Stored as real YAML files in `cks_kubernetes/` so they're easy to edit locally.
    # ----------------------------------------------------------------

    CONFIGMAP_MANIFEST = load_manifest("configmap.yaml")
    DEPLOYMENT_MANIFEST = load_manifest("deployment.yaml")
    SERVICE_MANIFEST = load_manifest("service.yaml")
    JOB_MANIFEST = load_manifest("job.yaml")


# ============================================================
# Header
# ============================================================


@app.cell(hide_code=True)
def _():
    mo.vstack(
        [
            banner(),
            about(
                "Kubernetes",
                """This notebook is a hands-on introduction to Kubernetes on CoreWeave Kubernetes Service (CKS).<br>
               Each section presents the actual YAML manifest, applies it declaratively, and then observes what the controllers do.<br>
               _If you are running this notebook in edit mode, start by running all cells in the bottom right._
            """,
            ),
            table_of_contents(
                [
                    {"title": "Cluster Access", "description": "Verify kubectl connectivity."},
                    {"title": "Environment and Namespace Setup", "description": "Create the lab namespace."},
                    {"title": "ConfigMap Lab", "description": "Apply, read, patch, and delete a ConfigMap."},
                    {"title": "Deployment Lab", "description": "Apply, scale, watch self-healing, and roll an update."},
                    {"title": "Service Lab", "description": "Expose a deployment and inspect endpoints."},
                    {"title": "Job Lab", "description": "Run a batch job to completion and inspect logs."},
                    {"title": "Cleanup", "description": "Delete lab resources and namespace."},
                ]
            ),
            security_disclaimer(),
        ]
    )
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
    mo.md(
        "---\n## Environment and Namespace Setup\n\n"
        "Create and verify a dedicated lab namespace. Every object below will live inside it, "
        "so deleting the namespace at the end cleans everything up at once."
    )
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    env_b1 = mo.ui.button(**RUN_BUTTON)
    env_b2 = mo.ui.button(**RUN_BUTTON)
    env_b3 = mo.ui.button(**RUN_BUTTON)
    env_b4 = mo.ui.button(**RUN_BUTTON)
    return env_b1, env_b2, env_b3, env_b4


@app.cell(hide_code=True)
def _(env_b1):
    step_cell(
        "1. Check API Server",
        "kubectl cluster-info",
        env_b1,
        env_b1.value > 0,
        explanation=(
            "`cluster-info` hits the Kubernetes API server and shows its address. "
            "The API server is the only component you talk to directly — everything else (controllers, kubelet, scheduler) "
            "reads and writes through it."
        ),
    )
    return


@app.cell(hide_code=True)
def _(env_b2):
    step_cell(
        "2. List Namespaces",
        "kubectl get namespace",
        env_b2,
        env_b2.value > 0,
        explanation="Namespaces partition cluster objects. You'll see system namespaces (`kube-system`, `kube-public`) alongside any others.",
    )
    return


@app.cell(hide_code=True)
def _(env_b3):
    step_cell(
        "3. Create Lab Namespace",
        f"kubectl create namespace {LAB_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -",
        env_b3,
        env_b3.value > 0,
        explanation=(
            f"Idempotently create `{LAB_NAMESPACE}`. The `--dry-run=client -o yaml | apply` pattern produces a manifest "
            "client-side and applies it — re-running won't error if the namespace already exists."
        ),
    )
    return


@app.cell(hide_code=True)
def _(env_b4):
    step_cell(
        "4. Verify Namespace Labels",
        f"kubectl get namespace {LAB_NAMESPACE} --show-labels",
        env_b4,
        env_b4.value > 0,
    )
    return


# ============================================================
# ConfigMap Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md(
        "---\n## ConfigMap Lab\n\n"
        "A ConfigMap stores non-secret key/value config. Below is the actual manifest — "
        "the API object Kubernetes stores. `kubectl create configmap ...` is just a shortcut "
        "that builds this YAML for you."
    )
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    cm_editor = mo.ui.code_editor(value=CONFIGMAP_MANIFEST, language="yaml", min_height=200, debounce=True)
    cm_b1 = mo.ui.button(**RUN_BUTTON)
    cm_b2 = mo.ui.button(**RUN_BUTTON)
    cm_b3 = mo.ui.button(**RUN_BUTTON)
    cm_b4 = mo.ui.button(**RUN_BUTTON)
    cm_b5 = mo.ui.button(**RUN_BUTTON)
    return cm_editor, cm_b1, cm_b2, cm_b3, cm_b4, cm_b5


@app.cell(hide_code=True)
def _(cm_editor, cm_b1):
    manifest_step_cell(
        "1. Apply ConfigMap Manifest",
        cm_editor,
        LAB_NAMESPACE,
        cm_b1,
        cm_b1.value > 0,
        explanation=(
            "Two top-level fields matter: `metadata` (identity — name, namespace, labels) "
            "and `data` (the key/value payload). Edit the YAML and re-click **Run** to see how "
            "`kubectl apply` reconciles your change."
        ),
    )
    return


@app.cell(hide_code=True)
def _(cm_b2):
    step_cell(
        "2. Read ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} get configmap {CONFIGMAP_NAME} -o yaml",
        cm_b2,
        cm_b2.value > 0,
        explanation=(
            "Notice the server added fields you didn't write — `creationTimestamp`, `resourceVersion`, `uid`. "
            "These are managed by the API server, not you."
        ),
    )
    return


@app.cell(hide_code=True)
def _(cm_b3):
    step_cell(
        "3. Patch ConfigMap Data (imperative drift)",
        f"""kubectl -n {LAB_NAMESPACE} patch configmap {CONFIGMAP_NAME} --type merge -p '{{"data":{{"MODE":"advanced","TOPIC":"crud"}}}}'""",
        cm_b3,
        cm_b3.value > 0,
        explanation=(
            "`patch` mutates the live object in-place. After this, the cluster state diverges from the YAML in step 1 — "
            "re-applying the manifest would revert `MODE` and remove `TOPIC`. This is the declarative-vs-imperative tension."
        ),
    )
    return


@app.cell(hide_code=True)
def _(cm_b4):
    step_cell(
        "4. Verify Patched ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} get configmap {CONFIGMAP_NAME} -o yaml",
        cm_b4,
        cm_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cm_b5):
    step_cell(
        "5. Delete ConfigMap",
        f"kubectl -n {LAB_NAMESPACE} delete configmap {CONFIGMAP_NAME} --ignore-not-found=true",
        cm_b5,
        cm_b5.value > 0,
    )
    return


# ============================================================
# Deployment Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md(
        "---\n## Deployment Lab\n\n"
        'A Deployment is a controller. You give it a desired state — _"I want N pods running this image"_ — '
        "and it creates a ReplicaSet, which in turn creates Pods. The controller continuously reconciles "
        "actual cluster state toward the spec. We'll watch that happen explicitly in step 4."
    )
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    dep_editor = mo.ui.code_editor(value=DEPLOYMENT_MANIFEST, language="yaml", min_height=320, debounce=True)
    dep_b1 = mo.ui.button(**RUN_BUTTON)
    dep_b2 = mo.ui.button(**RUN_BUTTON)
    dep_b3 = mo.ui.button(**RUN_BUTTON)
    dep_b4 = mo.ui.button(**RUN_BUTTON)
    dep_b5 = mo.ui.button(**RUN_BUTTON)
    dep_b6 = mo.ui.button(**RUN_BUTTON)
    dep_b7 = mo.ui.button(**RUN_BUTTON)
    dep_b8 = mo.ui.button(**RUN_BUTTON)
    return dep_editor, dep_b1, dep_b2, dep_b3, dep_b4, dep_b5, dep_b6, dep_b7, dep_b8


@app.cell(hide_code=True)
def _(dep_editor, dep_b1):
    manifest_step_cell(
        "1. Apply Deployment Manifest",
        dep_editor,
        LAB_NAMESPACE,
        dep_b1,
        dep_b1.value > 0,
        explanation=(
            "Three nested layers: the Deployment's `selector.matchLabels` finds Pods whose labels match. "
            "`template.metadata.labels` *stamps* those labels onto every Pod it creates. "
            "If the selector and template labels disagree, the Deployment refuses to start — try it."
        ),
    )
    return


@app.cell(hide_code=True)
def _(dep_b2):
    step_cell(
        "2. Scale to 2 Replicas",
        f"kubectl -n {LAB_NAMESPACE} scale deployment {DEPLOYMENT_NAME} --replicas=2",
        dep_b2,
        dep_b2.value > 0,
        explanation=(
            "Scaling changes the `spec.replicas` field on the Deployment. The controller notices the new desired count "
            "and creates one more Pod to match. (`scale` is imperative — equivalent to patching the field directly.)"
        ),
    )
    return


@app.cell(hide_code=True)
def _(dep_b3):
    step_cell(
        "3. Wait for Rollout",
        f"kubectl -n {LAB_NAMESPACE} rollout status deployment/{DEPLOYMENT_NAME} --timeout=120s",
        dep_b3,
        dep_b3.value > 0,
        explanation="Block until the Deployment reports that all desired Pods are ready.",
    )
    return


@app.cell(hide_code=True)
def _(dep_b4):
    reconcile_cmd = (
        f"echo '=== pods BEFORE delete ==='; "
        f"kubectl -n {LAB_NAMESPACE} get pods -l app={DEPLOYMENT_NAME} -o wide; "
        f"POD=$(kubectl -n {LAB_NAMESPACE} get pods -l app={DEPLOYMENT_NAME} "
        f"-o jsonpath='{{.items[0].metadata.name}}'); "
        f'echo; echo "=== deleting pod: $POD ==="; '
        f'kubectl -n {LAB_NAMESPACE} delete pod "$POD" --wait=false; '
        f"echo; echo '=== waiting 6s for the ReplicaSet controller to react ==='; sleep 6; "
        f"echo; echo '=== pods AFTER delete ==='; "
        f"kubectl -n {LAB_NAMESPACE} get pods -l app={DEPLOYMENT_NAME} -o wide"
    )
    step_cell(
        "4. Watch Self-Healing (delete a pod, observe replacement)",
        reconcile_cmd,
        dep_b4,
        dep_b4.value > 0,
        explanation=(
            "**This is the core idea of Kubernetes.** You deleted a Pod — but the Deployment's "
            "ReplicaSet still wants 2 Pods running. The controller detects the mismatch and creates a new Pod "
            "with a fresh name. Compare the `NAME` column before and after: one of the names will be new."
        ),
    )
    return


@app.cell(hide_code=True)
def _(dep_b5):
    step_cell(
        "5. Update Deployment Image",
        f"kubectl -n {LAB_NAMESPACE} set image deployment/{DEPLOYMENT_NAME} '*=nginx:1.27.5'",
        dep_b5,
        dep_b5.value > 0,
        explanation=(
            "Changes the image in `spec.template.spec.containers[*]`. The Deployment then creates a new ReplicaSet "
            "for the new image and scales the old one down — a rolling update, again driven by the controller."
        ),
    )
    return


@app.cell(hide_code=True)
def _(dep_b6):
    step_cell(
        "6. Wait for Updated Rollout",
        f"kubectl -n {LAB_NAMESPACE} rollout status deployment/{DEPLOYMENT_NAME} --timeout=120s",
        dep_b6,
        dep_b6.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b7):
    step_cell(
        "7. Read Deployment",
        f"kubectl -n {LAB_NAMESPACE} get deployment {DEPLOYMENT_NAME}",
        dep_b7,
        dep_b7.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(dep_b8):
    step_cell(
        "8. Read Deployment Pods",
        f"kubectl -n {LAB_NAMESPACE} get pods -l app={DEPLOYMENT_NAME}",
        dep_b8,
        dep_b8.value > 0,
    )
    return


# ============================================================
# Service Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md(
        "---\n## Service Lab\n\n"
        "A Service gives Pods a stable virtual IP and DNS name. Its `selector` is what wires it to Pods — "
        "the endpoints object is regenerated whenever matching Pods come and go."
    )
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    svc_editor = mo.ui.code_editor(value=SERVICE_MANIFEST, language="yaml", min_height=220, debounce=True)
    svc_b1 = mo.ui.button(**RUN_BUTTON)
    svc_b2 = mo.ui.button(**RUN_BUTTON)
    svc_b3 = mo.ui.button(**RUN_BUTTON)
    svc_b4 = mo.ui.button(**RUN_BUTTON)
    svc_b5 = mo.ui.button(**RUN_BUTTON)
    return svc_editor, svc_b1, svc_b2, svc_b3, svc_b4, svc_b5


@app.cell(hide_code=True)
def _(svc_editor, svc_b1):
    manifest_step_cell(
        "1. Apply Service Manifest",
        svc_editor,
        LAB_NAMESPACE,
        svc_b1,
        svc_b1.value > 0,
        explanation=(
            f"`spec.selector: app: {DEPLOYMENT_NAME}` is the only link between this Service and the Deployment's Pods — "
            "no foreign key, just label matching. Try changing the selector to a label no Pod has and re-run; "
            "the Endpoints in step 3 will go empty."
        ),
    )
    return


@app.cell(hide_code=True)
def _(svc_b2):
    step_cell(
        "2. Read Service",
        f"kubectl -n {LAB_NAMESPACE} get service {SERVICE_NAME} -o wide",
        svc_b2,
        svc_b2.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b3):
    step_cell(
        "3. Read Endpoints",
        f"kubectl -n {LAB_NAMESPACE} get endpoints {SERVICE_NAME}",
        svc_b3,
        svc_b3.value > 0,
        explanation=(
            "Endpoints are the actual Pod IPs the Service routes to. They were populated automatically "
            "from the selector — and they update as Pods come and go (try deleting a Pod and re-running this)."
        ),
    )
    return


@app.cell(hide_code=True)
def _(svc_b4):
    step_cell(
        "4. Patch Service Session Affinity",
        f"""kubectl -n {LAB_NAMESPACE} patch service {SERVICE_NAME} --type merge -p '{{"spec":{{"sessionAffinity":"ClientIP"}}}}'""",
        svc_b4,
        svc_b4.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(svc_b5):
    step_cell(
        "5. Read Service YAML",
        f"kubectl -n {LAB_NAMESPACE} get service {SERVICE_NAME} -o yaml",
        svc_b5,
        svc_b5.value > 0,
    )
    return


# ============================================================
# Job Lab
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md(
        "---\n## Job Lab\n\n"
        "A Job runs Pods to **completion** — the opposite of a Deployment, which restarts them forever. "
        "When a Job's Pod exits 0, the Job is done and the Pod stays around for log inspection."
    )
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    job_editor = mo.ui.code_editor(value=JOB_MANIFEST, language="yaml", min_height=280, debounce=True)
    job_b1 = mo.ui.button(**RUN_BUTTON)
    job_b2 = mo.ui.button(**RUN_BUTTON)
    job_b3 = mo.ui.button(**RUN_BUTTON)
    job_b4 = mo.ui.button(**RUN_BUTTON)
    return job_editor, job_b1, job_b2, job_b3, job_b4


@app.cell(hide_code=True)
def _(job_b1):
    step_cell(
        "1. Delete Old Job (if any)",
        f"kubectl -n {LAB_NAMESPACE} delete job {JOB_NAME} --ignore-not-found=true",
        job_b1,
        job_b1.value > 0,
        explanation="Jobs are immutable once `spec.template` is set, so we delete any previous run before re-applying.",
    )
    return


@app.cell(hide_code=True)
def _(job_editor, job_b2):
    manifest_step_cell(
        "2. Apply Job Manifest",
        job_editor,
        LAB_NAMESPACE,
        job_b2,
        job_b2.value > 0,
        explanation=(
            "`restartPolicy: Never` is required for Jobs (or `OnFailure`) — it tells the kubelet not to restart "
            "a Pod that exits. `backoffLimit: 2` caps retries if the Pod fails."
        ),
    )
    return


@app.cell(hide_code=True)
def _(job_b3):
    step_cell(
        "3. Wait for Completion",
        f"kubectl -n {LAB_NAMESPACE} wait --for=condition=complete --timeout=120s job/{JOB_NAME}",
        job_b3,
        job_b3.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(job_b4):
    step_cell(
        "4. Read Job Logs",
        f"kubectl -n {LAB_NAMESPACE} logs job/{JOB_NAME}",
        job_b4,
        job_b4.value > 0,
        explanation="The completed Pod is preserved so you can still read its logs after the Job is done.",
    )
    return


# ============================================================
# Cleanup
# ============================================================


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    mo.md("---\n## Cleanup\n\nDelete the lab namespace — every object inside it is cascaded away.")
    return


@app.cell(hide_code=True)
def _(kubectl_ready: bool):
    mo.stop(not kubectl_ready)
    cln_b1 = mo.ui.button(**RUN_BUTTON)
    cln_b2 = mo.ui.button(**RUN_BUTTON)
    cln_b3 = mo.ui.button(**RUN_BUTTON)
    return cln_b1, cln_b2, cln_b3


@app.cell(hide_code=True)
def _(cln_b1):
    step_cell(
        "1. List Remaining Namespace Resources",
        f"kubectl -n {LAB_NAMESPACE} get all || true",
        cln_b1,
        cln_b1.value > 0,
    )
    return


@app.cell(hide_code=True)
def _(cln_b2):
    step_cell(
        "2. Delete Lab Namespace",
        f"kubectl delete namespace {LAB_NAMESPACE} --ignore-not-found=true",
        cln_b2,
        cln_b2.value > 0,
        explanation="Deleting the namespace cascades to every object inside it — Pods, ReplicaSets, Services, Endpoints, ConfigMaps, Jobs.",
    )
    return


@app.cell(hide_code=True)
def _(cln_b3):
    step_cell(
        "3. Verify Namespace Removal",
        f"kubectl get namespace {LAB_NAMESPACE} || true",
        cln_b3,
        cln_b3.value > 0,
    )
    return


if __name__ == "__main__":
    app.run()
