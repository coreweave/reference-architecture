{{/*
Expand the name of the chart.
*/}}
{{- define "vllm-basic.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "vllm-basic.fullname" -}}
{{- if $.Values.fullnameOverride -}}
{{- $.Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else -}}
{{- $name := default .Chart.Name $.Values.nameOverride }}
{{- if contains .Release.Name $name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" }}
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
