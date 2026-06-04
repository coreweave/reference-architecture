{{/*
Expand the name of the chart.
*/}}
{{- define "vllm-basic.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "vllm-basic.fullname" -}}
{{- if $.Values.fullnameOverride -}}
{{- $.Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name $.Values.nameOverride -}}
{{- if contains .Release.Name $name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "vllm-basic.service.hostname" -}}
{{- if .Values.service.hostnameOverride -}}
{{- .Values.service.hostnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "vllm-basic.name" . -}}
{{- end -}}
{{- end -}}

{{/*
The port is shared between each probe so template it into each probe definition so it doesn't need to be copied.
*/}}
{{- define "vllm-basic.renderProbe" -}}
{{- $probe := .probe -}}
{{- $port := .port -}}
{{- $httpGet := merge $probe.httpGet (dict "port" $port) -}}
{{- $_ := set $probe "httpGet" $httpGet -}}
{{- toYaml $probe -}}
{{- end -}}

{{- /*
Define volumeMounts and volumes for vLLM containers
*/ -}}
{{- define "vllm-basic.volumeMounts" -}}
- name: dshm
  mountPath: /dev/shm
{{- if .Values.modelCache.enabled }}
- name: {{ .Values.modelCache.name }}
  mountPath: {{ .Values.modelCache.mountPath }}
{{- end }}
{{- if and .Values.vllm.zymtraceProfiler .Values.vllm.zymtraceProfiler.enabled }}
- name: zymtrace-cuda
  mountPath: {{ .Values.vllm.zymtraceProfiler.mountPath }}
{{- end }}
{{- end }}

{{- define "vllm-basic.volumes" -}}
- name: dshm
  emptyDir:
    medium: Memory
{{- if .Values.modelCache.enabled }}
- name: {{ .Values.modelCache.name }}
  persistentVolumeClaim:
    claimName: {{ .Values.modelCache.name | quote }}
{{- end -}}
{{- if and .Values.vllm.zymtraceProfiler .Values.vllm.zymtraceProfiler.enabled }}
- name: zymtrace-cuda
  hostPath:
    path: {{ .Values.vllm.zymtraceProfiler.hostPath }}
    type: Directory
{{- end }}
{{- end -}}

{{- /*
Define common environment variables for vLLM containers
*/ -}}
{{- define "vllm-basic.envVars" -}}
- name: NCCL_IB_HCA
  value: ibp
- name: NVIDIA_IMEX_CHANNELS
  value: "0"
{{- if .Values.hfToken.secretName }}
- name: HUGGING_FACE_HUB_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.hfToken.secretName | quote }}
      key: token
{{- else if .Values.hfToken.token }}
- name: HUGGING_FACE_HUB_TOKEN
  value: {{ .Values.hfToken.token | quote }}
{{- end -}}
{{- /* Create UCX_NET_DEVICES list matching number of GPUs */ -}}
{{- $gpuCount := int (index .Values.vllm.resources.limits "nvidia.com/gpu") -}}
{{- if gt $gpuCount 0 }}
{{- $devices := list -}}
{{- range $i := until $gpuCount }}
  {{- $devices = append $devices (printf "ibp%d:1" $i) -}}
{{- end }}
- name: UCX_NET_DEVICES
  value: {{ join "," $devices| quote }}
{{- end }}
{{- /* Operator-supplied extra env vars (TORCH_LOGS, NCCL_*, VLLM_*, etc.) */ -}}
{{- range $env := .Values.vllm.extraEnv }}
- name: {{ $env.name }}
  value: {{ $env.value | quote }}
{{- end }}
{{- /* zymtrace CUDA profiler injection (opt-in) */ -}}
{{- if and .Values.vllm.zymtraceProfiler .Values.vllm.zymtraceProfiler.enabled }}
- name: CUDA_INJECTION64_PATH
  value: {{ printf "%s/%s" .Values.vllm.zymtraceProfiler.mountPath .Values.vllm.zymtraceProfiler.implantLib | quote }}
{{- end }}
{{- end -}}
