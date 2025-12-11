{{/*
Expand the name of the chart.
*/}}
{{- define "cw-dragonfly.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "cw-dragonfly.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "cw-dragonfly.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "cw-dragonfly.labels" -}}
helm.sh/chart: {{ include "cw-dragonfly.chart" . }}
{{ include "cw-dragonfly.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "cw-dragonfly.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cw-dragonfly.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "cw-dragonfly.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "cw-dragonfly.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
CAIOS secret name
*/}}
{{- define "cw-dragonfly.caiosSecretName" -}}
'{{ include "cw-dragonfly.name" . }}-caios-secret'
{{- end }}

{{/*
CAIOS secret ref
*/}}
{{- define "cw-dragonfly.caiosSecretRef" -}}
{{- default ( include "cw-dragonfly.caiosSecretName" . ) .Values.existingCaiosSecretName }}
{{- end }}

{{/*
Default bucket prefix, if not specified
*/}}
{{- define "cw-dragonfly.caiosBucketRootPath" -}}
{{- default (include "cw-dragonfly.name" .) .Values.caiosBucketRootPath }}
{{- end }}

{{/*
DB password secret name
*/}}
{{- define "cw-dragonfly.dbPasswordSecretName" -}}
{{ include "cw-dragonfly.name" . }}-db-password
{{- end }}

{{/*
DB password secret ref
*/}}
{{- define "cw-dragonfly.dbPasswordSecretRef" -}}
{{- default ( include "cw-dragonfly.dbPasswordSecretName" . ) .Values.existingDbPasswordSecretName }}
{{- end }}

{{/*
backup-mover cmd
*/}}
{{- define "cw-dragonfly.backupMoverCmd" -}}
mkdir -p /crontab && mkdir -p /permanent-snapshots/$HOSTNAME && echo "TS=\$(date +%Y%m%d_%H%M%S) && mkdir /permanent-snapshots/$HOSTNAME/\$TS && cp /ephemeral-snapshots/*.dfs /permanent-snapshots/$HOSTNAME/\$TS/" > /cp_backups.sh && echo "{{ .Values.snapshotMoveCron }} /bin/sh /cp_backups.sh > /cp_backups.log 2>&1" > /crontab/root && crond -f -c /crontab -L /crond.log
{{- end }}

{{- define "retemplate" -}}
  {{- $value := index . 0 }}
  {{- $context := index . 1 }}
  {{- if typeIs "string" $value }}
      {{- tpl $value $context }}
  {{- else }}
      {{- tpl ($value | toYaml) $context }}
  {{- end }}
{{- end}}
