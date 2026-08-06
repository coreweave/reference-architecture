#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image= fs= source= options= nodes=
while [[ $# -gt 0 ]]; do case "$1" in --image) image="${2:-}";shift 2;;--mount-fs) fs="${2:-}";shift 2;;--mount-source) source="${2:-}";shift 2;;--mount-options) options="${2:-}";shift 2;;--nodes) nodes="${2:-}";shift 2;;*) printf 'error: unknown argument %s\n' "$1" >&2;exit 2;;esac;done
python3 - "$root/provisioner/local-path/repair/daemonset.template.yaml" "$image" "$fs" "$source" "$options" "$nodes" <<'PY'
import hashlib,json,re,sys
template,image,fs,source,options,nodes=sys.argv[1:]
def fail(msg): raise SystemExit('error: '+msg)
if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*@sha256:[a-f0-9]{64}',image): fail('image must be repository@sha256:64hex')
if not re.fullmatch(r'[A-Za-z0-9._+-]+',fs): fail('invalid mount filesystem')
if not source.startswith('/') or '\n' in source or '\r' in source: fail('mount source must be an absolute path')
parts=options.split(',')
if not parts or any(not re.fullmatch(r'[A-Za-z0-9._=-]+',x) or x in ('ro','rw') for x in parts) or len(set(parts))!=len(parts) or parts!=sorted(parts): fail('mount options must be canonical, safe, unique, and omit mode')
out=[]; names=set(); hosts=set()
try: lines=open(nodes,encoding='utf-8').read().splitlines()
except OSError as e: fail(str(e))
for line in lines:
    fields=line.split('\t')
    if len(fields)!=4: fail('nodes must be name<TAB>hostname<TAB>UID<TAB>providerID')
    name,host,uid,provider=fields
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',name) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or not re.fullmatch(r'[0-9a-f-]{8,}',uid) or not provider or '\n' in provider or '\r' in provider: fail('invalid node identity')
    if name in names or host in hosts: fail('duplicate node name or hostname')
    names.add(name);hosts.add(host);out.append({'name':name,'hostname':host,'uid':uid,'providerID':provider})
if not out: fail('nodes TSV is empty')
config={'mountFilesystem':fs,'mountOptions':parts,'mountSource':source,'nodes':out}
config_json=json.dumps(config,separators=(',',':'),sort_keys=True)
digest=hashlib.sha256(config_json.encode()).hexdigest(); name='kafka-local-pv-repair-config-'+digest[:16]
s=open(template).read(); values={'CONFIG_JSON_INDENTED':'      '+config_json,'CONFIG_MAP_NAME':name,'NODE_NAMES_JSON':json.dumps([x['name'] for x in out],separators=(',',':')),'CONFIG_HASH':digest,'IMAGE':image}
for key,value in values.items(): s=s.replace('__'+key+'__',value)
repair_dir=__import__('os').path.dirname(template)
print(open(__import__('os').path.join(repair_dir,'service-account.yaml')).read().rstrip())
print('---')
print(open(__import__('os').path.join(repair_dir,'rbac.yaml')).read().rstrip())
print('---')
print(s,end='')
PY
