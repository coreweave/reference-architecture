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
Workaround patches applied at Pod startup before any cosmos3 invocation.
Currently:
  - UPSTREAM_BUGS.md #9: cosmos3._src.imaginaire.utils.checkpoint_db._hf_download
    shells out to `uvx hf@1.13.0`, but huggingface_hub 1.13.0's CLI imports
    `click` without declaring it as a runtime dep. Inject "--with click" into
    the hardcoded uvx invocation. Idempotent.
Usage: {{ include "cosmos3.preludePatches" . }}
*/}}
{{- define "cosmos3.preludePatches" -}}
# --- upstream workarounds (see UPSTREAM_BUGS.md) ---
python - <<'__COSMOS3_PRELUDE_PATCHES__'
import pathlib
p = pathlib.Path("/workspace/cosmos3/_src/imaginaire/utils/checkpoint_db.py")
text = p.read_text()
if '"--with", "click"' not in text:
    p.write_text(text.replace(
        '"uvx",\n        f"hf@{HF_VERSION}",',
        '"uvx",\n        "--with", "click",\n        f"hf@{HF_VERSION}",',
        1,
    ))
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
