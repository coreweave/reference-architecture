{{/*
All Kubernetes resource names are derived from the Helm release name so that
multiple installs of this chart in the same cluster do not collide.

Usage: {{ include "zot-infra.caSecretName" . }}
*/}}

{{/* ── Internal CA ───────────────────────────────────────────────────────── */}}
{{- define "zot-infra.caName" -}}{{ .Release.Name }}-ca{{- end }}
{{- define "zot-infra.caSecretName" -}}{{ .Release.Name }}-ca-secret{{- end }}
{{- define "zot-infra.caIssuerName" -}}{{ .Release.Name }}-ca-issuer{{- end }}

{{/* ── Internal Gateway ──────────────────────────────────────────────────── */}}
{{- define "zot-infra.internalGwParamsName" -}}{{ .Release.Name }}-internal-gw-params{{- end }}
{{- define "zot-infra.internalGwName" -}}{{ .Release.Name }}-internal-gateway{{- end }}
{{- define "zot-infra.internalCertName" -}}{{ .Release.Name }}-internal-cert{{- end }}
{{- define "zot-infra.internalCertSecretName" -}}{{ .Release.Name }}-internal-cert-secret{{- end }}
{{- define "zot-infra.internalRouteName" -}}{{ .Release.Name }}-internal-route{{- end }}

{{/* ── External Gateway ──────────────────────────────────────────────────── */}}
{{- define "zot-infra.externalGwParamsName" -}}{{ .Release.Name }}-external-gw-params{{- end }}
{{- define "zot-infra.externalGwName" -}}{{ .Release.Name }}-external-gateway{{- end }}
{{- define "zot-infra.externalCertSecretName" -}}{{ .Release.Name }}-public-cert-secret{{- end }}
{{- define "zot-infra.externalRouteName" -}}{{ .Release.Name }}-external-route{{- end }}

{{/* ── DaemonSet ─────────────────────────────────────────────────────────── */}}
{{- define "zot-infra.dsName" -}}{{ .Release.Name }}-containerd-ds{{- end }}
{{- define "zot-infra.dsCmName" -}}{{ .Release.Name }}-containerd-hosts-cm{{- end }}
