#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' is not installed."
    exit 1
fi

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <original-pvc> <original-namespace> <new-namespace> [new-pvc-name]"
    exit 1
fi

ORIGINAL_PVC="$1"
ORIGINAL_NS="$2"
NEW_NS="$3"
NEW_PVC="${4:-$ORIGINAL_PVC}"

echo "Rebinding PVC '$ORIGINAL_PVC' from '$ORIGINAL_NS' to '$NEW_NS' as '$NEW_PVC'"
echo ""

ORIGINAL_PV=$(kubectl get pvc "$ORIGINAL_PVC" -n "$ORIGINAL_NS" -o jsonpath='{.spec.volumeName}')
if [[ -z "$ORIGINAL_PV" ]]; then
    echo "Error: Could not find PVC '$ORIGINAL_PVC' in namespace '$ORIGINAL_NS'"
    exit 1
fi
echo "Original PV: $ORIGINAL_PV"

PV_JSON=$(kubectl get pv "$ORIGINAL_PV" -o json)

VOLUME_HANDLE=$(echo "$PV_JSON" | jq -r '.spec.csi.volumeHandle')
STORAGE_CLASS=$(echo "$PV_JSON" | jq -r '.spec.storageClassName')
CAPACITY=$(echo "$PV_JSON" | jq -r '.spec.capacity.storage')
ACCESS_MODE=$(echo "$PV_JSON" | jq -r '.spec.accessModes[0]')
CSI_DRIVER=$(echo "$PV_JSON" | jq -r '.spec.csi.driver')

echo "  Volume Handle: $VOLUME_HANDLE"
echo "  Storage Class: $STORAGE_CLASS"
echo "  Capacity: $CAPACITY"
echo "  Access Mode: $ACCESS_MODE"
echo ""

NEW_PV="${ORIGINAL_PV}-share-${NEW_PVC}-${NEW_NS}"

echo "$PV_JSON" | jq -r '
    .spec.csi.volumeAttributes | 
    if . then 
        "    volumeAttributes:", 
        (to_entries[] | "      \(.key): \"\(.value)\"") 
    else empty end
' > pv_attributes.yaml

echo "$PV_JSON" | jq -r '
    .spec.mountOptions | 
    if . then 
        "  mountOptions:", 
        (.[] | "    - \(.)") 
    else empty end
' > pv_mount_options.yaml

cat > "${NEW_PV}.yaml" <<EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ${NEW_PV}
spec:
  capacity:
    storage: ${CAPACITY}
  accessModes:
    - ${ACCESS_MODE}
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ${STORAGE_CLASS}
  volumeMode: Filesystem
EOF

if [[ -s pv_mount_options.yaml ]]; then
    cat pv_mount_options.yaml >> "${NEW_PV}.yaml"
fi

cat >> "${NEW_PV}.yaml" <<EOF
  csi:
    driver: ${CSI_DRIVER}
    volumeHandle: ${VOLUME_HANDLE}
    readOnly: false
EOF

if [[ -s pv_attributes.yaml ]]; then
    cat pv_attributes.yaml >> "${NEW_PV}.yaml"
fi

cat > "${NEW_PVC}-${NEW_NS}.yaml" <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${NEW_PVC}
  namespace: ${NEW_NS}
spec:
  accessModes:
    - ${ACCESS_MODE}
  resources:
    requests:
      storage: ${CAPACITY}
  storageClassName: ${STORAGE_CLASS}
  volumeName: ${NEW_PV}
EOF

rm -f pv_attributes.yaml pv_mount_options.yaml

echo ""
echo "Manifests created successfully!"
echo ""
echo "To apply:"
echo "  kubectl apply -f ${NEW_PV}.yaml"
echo "  kubectl apply -f ${NEW_PVC}-${NEW_NS}.yaml"
echo ""
echo "To verify:"
echo "  kubectl get pvc ${NEW_PVC} -n ${NEW_NS}"