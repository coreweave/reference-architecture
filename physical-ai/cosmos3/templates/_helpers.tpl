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
In-Pod workaround patches applied before any cosmos_framework invocation.
Currently patches `cosmos_framework.inference.ray.serve`'s `ray.serve.run(...)`
call to add `http_options=HTTPOptions(host="0.0.0.0", port=8000, request_timeout_s=1800)`.
Upstream binds to 127.0.0.1 by default, which is unreachable from a K8s
Service. Pending upstream PR.
Usage: {{ include "cosmos3.preludePatches" . }}
*/}}
{{- define "cosmos3.preludePatches" -}}
# --- upstream workarounds ---
python - <<'__COSMOS3_PRELUDE_PATCHES__'
import pathlib, re
p = pathlib.Path("/workspace/cosmos_framework/inference/ray/serve.py")
text = p.read_text()
needle = 'ray.serve.run(router_app, name="cosmos3_omni", blocking=True)'
patched = (
    'import ray.serve.config as _cw_serve_config\n'
    '    ray.serve.start(http_options=_cw_serve_config.HTTPOptions(\n'
    '        host="0.0.0.0", port=8000, request_timeout_s=1800,\n'
    '    ))\n'
    '    ' + needle
)
if needle in text and 'host="0.0.0.0"' not in text:
    p.write_text(text.replace(needle, patched, 1))
__COSMOS3_PRELUDE_PATCHES__
# --- end upstream workarounds ---
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
