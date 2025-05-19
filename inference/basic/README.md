# Basic Inference Reference Architecture

This repository provides a Helm chart to deploy a basic inference setup on CoreWeave's infrastructure. Follow the steps below to set up the required dependencies in your cluster and install this chart.

## Prerequisites

Before installing this chart, ensure you have the following:
- A Kubernetes cluster on CoreWeave.
- `kubectl` and `helm` installed and configured to interact with your cluster.

## Setup

### 0. Add CoreWeave's Helm Repository
Add CoreWeave's Helm repository to your local Helm client:

```bash
helm repo add coreweave https://charts.core-services.ingress.coreweave.com
helm repo update
```

### 1. Install Ingress

Usage of an ingress controller is recommended with this chart. The rest of this example will use CoreWeave's Traefik chart. Find more details about it [here](https://docs.coreweave.com/docs/products/cks/how-to/coreweave-charts/traefik).

If you don't require TLS certificates, you can skip most of this section and simply run the following command to install Traefik:

```bash
# Skip this if you plan to use cert-manager
helm install traefik coreweave/traefik --namespace traefik --create-namespace
```

If you do require TLS certificates, you can use cert-manager to manage them. Skip the command above and follow the following instructions in sections 1.a and 1.b.

#### 1.a TLS Support with cert-manager

Cert-Manager is a simple way to manage TLS certificates. Like Traefik, CoreWeave publishes an easy to use chart. You can find the docs on it [here](https://docs.coreweave.com/docs/products/cks/how-to/coreweave-charts/cert-manager).

You can customize the cert-issuers that traefik will use if you wish, but otherwise you can use the defaults and install with the following commands:

```bash
helm install cert-manager coreweave/cert-manager --namespace cert-manager --create-namespace
helm upgrade cert-manager coreweave/cert-manager --namespace cert-manager --set cert-issuers.enabled=true 
```

Once cert-manager is installed, you can install traefik with values configured to use the cert issuers.

#### 1.b Traefik

To install it, first create the `values-traefik.yaml` file or use the one in [hack/values-traefik.yaml](./hack/values-traefik.yaml):

```yaml
tls:
  enabled: true
  clusterIssuer: letsencrypt-prod
  labels:
     cert-manager.io/cluster-issuer: letsencrypt-prod
  annotations:
     cert-manager.io/cluster-issuer: letsencrypt-prod
```

You can install it using the following command:

```bash
helm install traefik coreweave/traefik --namespace traefik --create-namespace -f hack/values-traefik.yaml
```

### 2. Observability
Basic setup to enable observability for the vLLM deployment. This includes installing Prometheus and a Grafana dashboard.

#### 2.a Install Prometheus
You will need Prometheus and Grafana to monitor the vLLM deployment. There are manifests in [hack/manifests-prometheus.yaml](./hack/manifests-prometheus.yaml) to install prometheus. You can run the following command to install it:

```bash
kubectl apply -f hack/manifests-prometheus.yaml
```
This will create a `monitoring` namespace and install prometheus into it. You can check the status of the pods with:

```bash
kubectl get pods -n monitoring
```

**IMPORTANT**: If you modify the files and change the installation namespace, or if you already have a prometheus installation and skip this step, you will need to update the `prometheus` section of the chart values to point to your prometheus installation namespace.

**FOR DEBUGGING ONLY**, you can access the prometheus UI by port-forwarding the prometheus service:
```bash
kubectl port-forward -n monitoring prometheus-k8s-0 9090:9090
```
Then you can access the prometheus UI at `http://localhost:9090`.

Later, the helm chart in this repo will automatically expose the prometheus service for metrics visualization in Grafana.

#### 2.b Create a ConfigMap with a Grafana Dashboard for vLLM
You can create a ConfigMap with a Grafana dashboard for vLLM. This will allow you to visualize the metrics collected by Prometheus. You can find the dashboard JSON in [hack/manifests-grafana.yaml](./hack/manifests-grafana.yaml). Apply the configmap with the following command:

```bash
kubectl apply -f hack/manifests-grafana.yaml -n RELEASE_NAMESPACE
```
This will create a `grafana-dashboard` configmap in your release namespace. Later when we deploy Grafana using the chart, it will automatically load this dashboard. You can create the namespace now if it doesn't exist yet with `kubectl create namespace RELEASE_NAMESPACE`. For the rest of this guide, we will use `inference` as the `RELEASE_NAMESPACE`, but you can change it to whatever you want.

### 2.c Autoscaling
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

### 3. Huggingface tokens

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

### 4. Model Cache PVC

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

```bash
kubectl apply -f huggingface-model-cache.yaml
```

Once applied, you can configure the model cache section of the chart values like this:

```yaml
modelCache:
  enabled: true
  create: false
  name: huggingface-model-cache
```

### 5. Verify Dependencies

Ensure that all of the dependencies exist with the following commands

```bash
kubectl get pods -n traefik
kubectl get pods -n cert-manager
kubectl get pods -n monitoring
kubectl get pods -n keda
kubectl get pvc -n inference
kubectl get secret -n inference
```

### 6. LeaderWorkerSet (Optional)

If you want to run vLLM multi-node then you need to install LeaderWorkerSet into your CKS cluster.

Further details are in the kubernetes docs [here](https://lws.sigs.k8s.io/docs/installation/).

## Installing the Basic Inference Chart

Once the prerequisites are set up, you can install this chart. Take a look at the `values.yaml` file to see all that you can adjust. 

### Full examples

There are example values files in the `hack/` folder that you can use.

These examples expect that everything in the prereq steps are already installed. Also, before you can apply the example values files you need to update `ingress.clusterName` and `ingress.orgID` with the info for the CKS cluster you are using.

For example, to run `meta-llama/Llama-3.1-8B-Instruct` you can use `hack/values-llama-small.yaml`:

```bash
helm install basic-inference ./ --namespace inference --create-namespace -f hack/values-llama-small.yaml
```

By default, the chart will create three ingress objects:
1. The main ingress for the vLLM service (uses the release name)
2. The Grafana ingress (called `grafana`) with basic auth.
3. The prometheus ingress (called `prometheus`) with basic auth. Default username and password are `admin` and `cwadmin`. You can change this in the values file. To get a new credentials value, run the following command: `htpasswd -nb USERNAME PASSWORD`

## Using the Service

Once the helm chart is deployed, you can query the endpoint using the standard OpenAI API spec.

If you followed the installation steps above and created a Traefik ingress, you can retrieve the endpoint via kubectl by looking at the `ingress`. In the following example, the endpoint to query would be `navs-vllm.cw2025-training.coreweave.app`.

If you installed and used cert-manager as the instructions recommend, you can use `https`.

```bash
❯ kubectl get ingress                                                                                                                                                         
NAME       CLASS     HOSTS                                     ADDRESS         PORTS     AGE
deepseek   traefik   `navs-vllm.cw2025-training.coreweave.app`   166.19.16.127   80, 443   7d14h
❯ export VLLM_ENDPOINT="https://navs-vllm.cw2025-training.coreweave.app"
```

### cURL

Assuming the ingress endpoint is stored in an environment variable named `VLLM_ENDPOINT`, you can use the following queries.

First, check that the service is healthy. If this returns a `200` the service is healthy

```bash
❯ curl -s -o /dev/null -w "%{http_code}" $VLLM_ENDPOINT/health
200
```

Then you can get the current active models:

```bash
❯ curl -s $VLLM_ENDPOINT/v1/models | jq '.data[].id'
"deepseek-ai/DeepSeek-R1"
❯ export VLLM_MODEL="deepseek-ai/DeepSeek-R1"
```

Finally you can run inference against the model:

```bash
❯ curl -X POST "$VLLM_ENDPOINT/v1/chat/completions" \
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
CoreWeave provides a chart to install grafana. This chart was used as a subchart in this inference solution. You can find the docs [here](https://docs.coreweave.com/docs/observability/self-hosted-grafana).

Log into Grafana using the following credentials:
- Username: `admin`
- Password: obtain it with the command `kubectl get secret {{RELEASE_NAME}}-grafana -n inference -o=jsonpath='{.data.admin-password}' | base64 --decode; echo`
  - Your release name is likely `basic-inference`, so your command would be `kubectl get secret basic-inference-grafana -n inference -o=jsonpath='{.data.admin-password}' | base64 --decode; echo`

You can continue following the steps in the link above ([this one](https://docs.coreweave.com/docs/observability/self-hosted-grafana)) to set up CoreWeave dashboards and a data source; however, this is not required for the vLLM chart to work. For the purposes of this example, you can simply add the local prometheus data source and the `vLLM` dashboard.

To add the data source, go to Grafana and click on the connections section on the left sidebar. Then click on `Data Sources` and `+ Add a new data source`. Select `Prometheus` and set the URL to `https://prometheus.ORG_ID-CLUSTER_NAME.coreweave.app` (replace with your cluster name and org ID). You can also check the prometheus IngressRoute in the `monitoring` namespace to get the URL. For Authentication, select `Basic Auth` and set the username and password to `admin` and `cwadmin` (unless you changed them in the steps above). Click on `Save & Test` to save the data source.

Now you can go to the dashboards and select the vLLM dashboard. Dashboard might take a while to be loaded from k8s configmaps. If you don't see yours, please wait a few minutes and refresh the page.

### Autoscaling Test
The sample deployment is configured to use KEDA for autoscaling. You can test this by running the following command (replace model with your model if you didn't use the small-sample `meta-llama/Llama-3.1-8B-Instruct`):
```bash
cd hack/tests
python load-test.py \
  --endpoint "$VLLM_ENDPOINT/v1" \
  --model "meta-llama/Llama-3.1-8B-Instruct" \
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
helm uninstall cert-manager --namespace cert-manager
helm uninstall traefik --namespace traefik
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
- [ ] Auth
- [ ] Remove ray[data] pip install from command when vLLM container has it built in
