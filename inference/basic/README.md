# Basic Inference Reference Architecture

This repository provides a Helm chart to deploy a basic inference setup on CoreWeave's infrastructure. Follow the steps below to set up the required dependencies in your cluster and install this chart.

## Prerequisites

Before installing this chart, ensure you have the following:
- A Kubernetes cluster on CoreWeave.
- `kubectl` and `helm` installed and configured to interact with your cluster.

## Setup

### 0. Add CoreWeave's Helm Repository
Add CoreWeave's Helm repository to your local Helm client if you haven't already:

```bash
helm repo add coreweave https://charts.core-services.ingress.coreweave.com
helm repo update
```

### 1. Set up Observability and Ingress
Follow the steps in the [Observability Setup](../../observability/basic/README.md) to install Prometheus and Grafana, which are required for monitoring and visualization of metrics.

### 2. Create a ConfigMap with a Grafana Dashboard for vLLM
You can create a ConfigMap with a Grafana dashboard for vLLM. This will allow you to visualize the metrics collected by Prometheus. You can find the dashboard JSON in [hack/manifests-grafana.yaml](./hack/manifests-grafana.yaml).

You can create the namespace now if it doesn't exist yet with `kubectl create namespace inference`.

Then apply the configmap with the following command:

```bash
kubectl apply -f hack/manifests-grafana.yaml -n inference
```

This will create a `grafana-dashboard` configmap in the `inference` namespace (default name for the `RELEASE_NAMESPACE`). Grafana will automatically load this dashboard. 

### 3. Autoscaling
You can enable horizontal pod autoscaling for the vLLM deployment, but you will need to install [keda](https://keda.sh/docs/latest/) to do so. KEDA is a Kubernetes-based event-driven autoscaler.

First add the KEDA helm repository:

```bash
helm repo add kedacore https://kedacore.github.io/charts  
helm repo update
```
Then install KEDA with the following command:
```bash
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 4. Huggingface tokens

Some models on huggingface require you do be authed into an account that has been granted access. You can easily do this by using a huggingface token.

The chart allows you to specify the secret token in plain text but it is recommended that you create a huggingface token secret separately and reference it outside of this chart. This also allows you to use the same token for all vLLM deployments.

Once you fetch a token from HuggingFace [here](https://huggingface.co/settings/tokens), create a kubernetes secret with the following command:

```bash
export HF_TOKEN="<huggingface-token>"
kubectl create secret generic hf-token -n inference --from-literal=token="$HF_TOKEN"
```

Now you can use the following in the values for the basic inference chart:

```yaml
hfToken:
  secretName: "hf-token"
```

### 5. Model Cache PVC

Similar to the HuggingFace token, the chart has functionality to create a PVC for you but it is recommended you create one outside the scope of the helm chart so it can persist across deployments and be reused.

To create one manually, apply the following yaml:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: huggingface-model-cache
  namespace: inference
spec:
  accessModes:
  - ReadWriteMany
  resources:
    requests:
      storage: 10Ti
  storageClassName: shared-vast
```

You can use the one in the `hack/` folder if you don't plan to make any changes.
```bash
kubectl apply -f hack/huggingface-model-cache.yaml
```

Once applied, you can configure the model cache section of the chart values like this:

```yaml
modelCache:
  enabled: true
  create: false
  name: huggingface-model-cache
```

### 6. Verify Dependencies

Ensure that all of the dependencies exist with the following commands

```bash
kubectl get pods -n monitoring
kubectl get pods -n keda
kubectl get pvc -n inference
kubectl get secret -n inference
```

### 7. LeaderWorkerSet (Optional)

If you want to run vLLM multi-node then you need to install LeaderWorkerSet into your CKS cluster.

Further details are in the kubernetes docs [here](https://lws.sigs.k8s.io/docs/installation/).

## Installing the Basic Inference Chart

Once the prerequisites are set up, you can install this chart. Take a look at the `values.yaml` file to see all that you can adjust. 

### Full examples

There are example values files in the `hack/` folder that you can use.

These examples expect that everything in the prereq steps are already installed. Also, before you can apply the example values files you need to update `ingress.clusterName` and `ingress.orgID` with the info for the CKS cluster you are using.

Please note that if you updated any of the default values for the observability chart installation, you may need to update the `prometheus.serverURL` value from the default `http://prometheus-operated.monitoring:9090` to the correct URL for your Prometheus instance.

For example, to run `meta-llama/Llama-3.1-8B-Instruct` you can use `hack/values-llama-small.yaml`:

```bash
helm install basic-inference ./ --namespace inference --create-namespace -f hack/values-llama-small.yaml
```

By default, the chart will create an ingress for the vLLM service which uses the release name as subdomain.

## Using the Service

Once the helm chart is deployed, you can query the endpoint using the standard OpenAI API spec.

If you followed the installation steps above and created a Traefik ingress, you can retrieve the endpoint via kubectl by looking at the `ingress`. In the following example, the endpoint to query would be `basic-inference.cw2025-training.coreweave.app`.

If you followed the instructions, you can use `https` because cert-manager was installed in your cluster.

```bash
export VLLM_ENDPOINT="$(kubectl get ingress basic-inference -n inference -o=jsonpath='{.spec.rules[0].host}')"
```

### cURL

Assuming the ingress endpoint is stored in an environment variable named `VLLM_ENDPOINT`, you can use the following queries.

First, check that the service is healthy. If this returns a `200` the service is healthy

```bash
curl -s -o /dev/null -w "%{http_code}" $VLLM_ENDPOINT/health
# Response should be `200`
```

Then you can get the current active models:

```bash
export VLLM_MODEL="$(curl -s $VLLM_ENDPOINT/v1/models | jq -r '.data[].id')"
echo $VLLM_MODEL
# meta-llama/Llama-3.1-8B-Instruct
```

Finally you can run inference against the model:

```bash
curl -X POST "$VLLM_ENDPOINT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "'"$VLLM_MODEL"'",
        "messages": [
          { "role": "system", "content": "You are a helpful assistant and an expert in modern AI infrastructure." },
          { "role": "user",   "content": "Explain why HGX H200 nodes suit large-MoE models." }
        ]
      }'
```

### OpenAI Client Library

Most application use the OpenAI libraries across various languages to run inference. Since vLLM is running with the OpenAI API spec you can use it here.

All you need to do is adjust the base URL used with the library.

#### Python Example

First instantiate the OpenAI client. Make sure you adjust the model and base URL. You can find the values by following the steps in the cURL section. 

```python
MODEL = "deepseek-ai/DeepSeek-R1"
client = OpenAI(
    base_url="https://navs-vllm.cw2025-training.coreweave.app/v1",
    api_key="unused",
)
```

Then you can use the client as you would normally.

Chat completion example:

```python
chat = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Explain why HGX H200 nodes suit large-MoE models."},
    ],
    temperature=0.5
)
print(chat.choices[0].message.content)
```

Streaming example:

```python
stream = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "What would a GPU cloud provider have to do to receive the highest ranking in the SemiAnalysis ClusterMAX award?"}],
    stream=True,                # yields chunks as they arrive
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Access Metrics in Grafana
Open the Grafana instance you set up in the Observability Setup section. You can access it via the Ingress URL you configured.
You can find the Grafana URL by running:
```bash
kubectl get ingress observability-grafana -n monitoring -o=jsonpath='{.spec.rules[0].host}' ; echo
```

Now you can go to the dashboards and select the vLLM dashboard. Dashboard might take a while to be loaded from k8s configmaps. If you don't see yours, please wait a few minutes and refresh the page.

### Autoscaling Test
The sample deployment is configured to use KEDA for autoscaling. You can test this by running the following command (replace model with your model if you didn't use the small-sample `meta-llama/Llama-3.1-8B-Instruct`):
```bash
cd hack/tests
python load-test.py \
  --endpoint "https://$VLLM_ENDPOINT/v1" \
  --model "$VLLM_MODEL" \
  --prompts-file prompts.txt \
  --concurrency 256 \
  --requests 1024 \
  --out results.json
```

The autoscaler will scale the number of replicas based on the KV Cache usage of the deployments. If you monitor your cache utilization metric in the Grafana dashboard (see previous section), you should see the number of replicas increase and decrease based on the load. The load will spread among the replicas.

## Cleanup

To uninstall the chart and its dependencies, run:

```bash
helm uninstall basic-inference --namespace inference
helm uninstall observability --namespace monitoring
helm uninstall keda --namespace keda
```

If you manually installed your huggingface token and model cache, clean those up as well:

```bash
kubectl delete -f huggingface-model-cache.yaml
kubectl delete secret hf-token
```

# ToDo

- [X] Autoscaling
- [X] vLLM Metrics
- [ ] Routing to different models
- [ ] Object storage
- [ ] Tensorizer
- [X] Multi-node
- [ ] Autoscaling multi-node
- [ ] Auth
- [ ] Remove ray[data] pip install from command when vLLM container has it built in
