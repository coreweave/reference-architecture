{{/*
Resource block for a given GPU count.
Usage: {{ include "cosmos3.resources" (dict "gpu" 8) | nindent 12 }}
*/}}
{{- define "cosmos3.resources" -}}
{{- $gpu := int .gpu -}}
{{- if eq $gpu 0 }}
requests:
  cpu: "4"
  memory: 16Gi
limits:
  cpu: "8"
  memory: 32Gi
{{- else if eq $gpu 1 }}
requests:
  cpu: "8"
  memory: 64Gi
  nvidia.com/gpu: "1"
limits:
  cpu: "16"
  memory: 128Gi
  nvidia.com/gpu: "1"
{{- else if eq $gpu 8 }}
requests:
  cpu: "32"
  memory: 512Gi
  nvidia.com/gpu: "8"
limits:
  cpu: "64"
  memory: 1024Gi
  nvidia.com/gpu: "8"
{{- end }}
{{- end -}}

{{/*
Standard env block — HF token + HF_HOME, plus any extraEnv on the step.
Usage: {{ include "cosmos3.env" $step | nindent 12 }}
*/}}
{{- define "cosmos3.env" -}}
- name: HF_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .hfSecretName | default "hf-token" }}
      key: HF_TOKEN
- name: HF_HOME
  value: /mnt/cosmos3/hf_cache
{{- range $k, $v := .extraEnv }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
{{- end -}}

{{/*
Standard volumeMounts — shared PVC always, dshm only if dshmSize is set.
Usage: {{ include "cosmos3.volumeMounts" $step | nindent 12 }}
*/}}
{{- define "cosmos3.volumeMounts" -}}
- name: cosmos3-shared
  mountPath: /mnt/cosmos3
{{- if .dshmSize }}
- name: dshm
  mountPath: /dev/shm
{{- end }}
{{- end -}}

{{/*
Standard volumes — shared PVC always, dshm only if dshmSize is set.
Usage: {{ include "cosmos3.volumes" (dict "pvcName" .Values.pvc.name "dshmSize" $step.dshmSize) | nindent 8 }}
*/}}
{{- define "cosmos3.volumes" -}}
- name: cosmos3-shared
  persistentVolumeClaim:
    claimName: {{ .pvcName }}
{{- if .dshmSize }}
- name: dshm
  emptyDir:
    medium: Memory
    sizeLimit: {{ .dshmSize }}
{{- end }}
{{- end -}}
