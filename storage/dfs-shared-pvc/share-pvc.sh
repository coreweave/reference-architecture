#!/usr/bin/env bash

set -euo pipefail

# DFS Shared PVC Script - Full Lifecycle Management
# Manage sharing of distributed file storage (DFS) volumes across Kubernetes namespaces
# Requires VAST CSI driver (csi.vastdata.com)

VERSION="1.0.0"
VAST_CSI_DRIVER="csi.vastdata.com"
STORAGE_CLASS="shared-vast"
SCRIPT_LABEL="coreweave.com/shared-by=dfs-shared-pvc-script"

# Global usage
usage_global() {
    cat << EOF
Usage: $(basename "$0") <command> [options]

Manage DFS (distributed file storage) PVC sharing across Kubernetes namespaces.
Requires VAST CSI driver for source PVCs.

Commands:
  apply       Create or update shared PVCs (from CLI args or manifest)
  list        List existing shared PVCs
  validate    Validate manifest or check existing shares
  delete      Remove shared PVCs
  reconcile   Ensure actual state matches manifest
  help        Show help for a command

Options:
  -h, --help     Show this help message
  --version      Show version information

Examples:
  # Create shares from command line
  $(basename "$0") apply -s data -n prod -t data -N dev

  # Create shares from manifest
  $(basename "$0") apply -f shares.yaml

  # List all shares from a source
  $(basename "$0") list --source prod/data

  # Validate a manifest
  $(basename "$0") validate -f shares.yaml

  # Delete all shares from a source
  $(basename "$0") delete --source prod/data

  # Reconcile state with manifest
  $(basename "$0") reconcile -f shares.yaml

Run '$(basename "$0") help <command>' for more information on a command.

EOF
    exit 0
}

# Command-specific usage
usage_apply() {
    cat << EOF
Usage: $(basename "$0") apply [OPTIONS]

Create or update shared PVCs from command-line arguments or a manifest file.

From Command Line:
  -s, --source-pvc NAME         Source PVC name
  -n, --source-namespace NS     Source namespace
  -t, --target-pvc NAME         Target PVC name (repeatable)
  -N, --target-namespace NS     Target namespace (repeatable)
  -r, --read-only              Make preceding target read-only

From Manifest:
  -f, --file FILE              YAML manifest file

Common Options:
  -l, --label KEY=VALUE        Additional label (repeatable)
  --dry-run                    Show what would be created
  -v, --verbose                Verbose output
  -h, --help                   Show this help

Examples:
  # From command line
  $(basename "$0") apply -s data -n prod -t data -N dev -t data-ro -N qa --read-only

  # From manifest
  $(basename "$0") apply -f shares.yaml --dry-run

Manifest Format:
  apiVersion: v1
  kind: DFSShareConfig
  metadata:
    name: my-shares
  source:
    pvc: data-volume
    namespace: production
  targets:
    - pvc: data-volume
      namespace: development
      readOnly: false
    - pvc: data-readonly
      namespace: analytics
      readOnly: true
  labels:
    team: platform
    owner: ops-team

EOF
    exit 0
}

usage_list() {
    cat << EOF
Usage: $(basename "$0") list [OPTIONS]

List existing shared PVCs and their status.

Options:
  --source NS/PVC              Filter by source (format: namespace/pvc-name)
  --target NS                  Filter by target namespace
  --output FORMAT              Output format: table (default), json, yaml
  -v, --verbose                Show detailed information
  -h, --help                   Show this help

Examples:
  # List all shares
  $(basename "$0") list

  # List shares from specific source
  $(basename "$0") list --source production/data

  # List shares in target namespace
  $(basename "$0") list --target dev

  # JSON output
  $(basename "$0") list --output json

EOF
    exit 0
}

usage_validate() {
    cat << EOF
Usage: $(basename "$0") validate [OPTIONS]

Validate manifest syntax and check state of existing shares.

Options:
  -f, --file FILE              Manifest file to validate
  --source NS/PVC              Validate specific source
  --check-drift                Check for configuration drift
  -v, --verbose                Show detailed validation
  -h, --help                   Show this help

Examples:
  # Validate manifest syntax
  $(basename "$0") validate -f shares.yaml

  # Check drift for a source
  $(basename "$0") validate --source prod/data --check-drift

EOF
    exit 0
}

usage_delete() {
    cat << EOF
Usage: $(basename "$0") delete [OPTIONS]

Delete shared PVCs (removes derived PVs and PVCs, not source).

Options:
  --source NS/PVC              Delete all shares from this source
  --target NS/PVC              Delete specific target (format: namespace/pvc-name)
  --all                        Delete all managed shares (requires confirmation)
  --force                      Skip confirmation prompts
  --dry-run                    Show what would be deleted
  -v, --verbose                Verbose output
  -h, --help                   Show this help

Examples:
  # Delete all shares from a source
  $(basename "$0") delete --source prod/data

  # Delete specific target
  $(basename "$0") delete --target dev/data-shared

  # Dry run
  $(basename "$0") delete --source prod/data --dry-run

EOF
    exit 0
}

usage_reconcile() {
    cat << EOF
Usage: $(basename "$0") reconcile [OPTIONS]

Ensure actual state matches desired state in manifest.
Creates missing resources, updates changed ones, optionally removes extras.

Options:
  -f, --file FILE              Manifest file
  --prune                      Delete shares not in manifest
  --dry-run                    Show what would change
  -v, --verbose                Verbose output
  -h, --help                   Show this help

Examples:
  # Reconcile to match manifest
  $(basename "$0") reconcile -f shares.yaml

  # Show what would change
  $(basename "$0") reconcile -f shares.yaml --dry-run

  # Reconcile and remove extras
  $(basename "$0") reconcile -f shares.yaml --prune

EOF
    exit 0
}

# Logging functions
log_info() {
    echo "[INFO] $*"
}

log_success() {
    echo "[SUCCESS] $*"
}

log_warn() {
    echo "[WARN] $*" >&2
}

log_error() {
    echo "[ERROR] $*" >&2
}

log_verbose() {
    if [[ "${VERBOSE:-false}" == "true" ]]; then
        echo "[DEBUG] $*"
    fi
}

# Check prerequisites
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found"
        exit 1
    fi
    if ! kubectl cluster-info &> /dev/null; then
        log_error "kubectl not connected to cluster"
        exit 1
    fi
    log_verbose "kubectl connected"
}

# Parse YAML manifest using pure bash/awk/sed
parse_manifest() {
    local file="$1"
    
    if [[ ! -f "$file" ]]; then
        log_error "Manifest file not found: $file"
        exit 1
    fi
    
    # Parse source section using awk
    local source_pvc source_ns
    source_pvc=$(awk '/^source:/{flag=1;next}/^[^ ]/{flag=0}flag&&/pvc:/{sub(/.*pvc:[[:space:]]*/, ""); print; exit}' "$file")
    source_ns=$(awk '/^source:/{flag=1;next}/^[^ ]/{flag=0}flag&&/namespace:/{sub(/.*namespace:[[:space:]]*/, ""); print; exit}' "$file")
    
    if [[ -z "$source_pvc" || -z "$source_ns" ]]; then
        log_error "Could not parse source from manifest (pvc: '$source_pvc', namespace: '$source_ns')"
        exit 1
    fi
    
    echo "SOURCE_PVC=$source_pvc"
    echo "SOURCE_NAMESPACE=$source_ns"
    
    # Parse targets
    local in_targets=false line_num=0
    while IFS= read -r line; do
        ((line_num++))
        
        # Detect targets section
        if [[ "$line" =~ ^targets: ]]; then
            in_targets=true
            continue
        fi
        
        # Exit targets section
        if [[ "$in_targets" == "true" && "$line" =~ ^[a-zA-Z] ]]; then
            break
        fi
        
        # Parse target entries
        if [[ "$in_targets" == "true" ]]; then
            if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*pvc: ]]; then
                local pvc=$(echo "$line" | sed 's/.*pvc: *//' | sed 's/ *$//')
                echo "TARGET_PVC=$pvc"
            elif [[ "$line" =~ ^[[:space:]]*namespace: ]]; then
                local ns=$(echo "$line" | sed 's/.*namespace: *//' | sed 's/ *$//')
                echo "TARGET_NAMESPACE=$ns"
            elif [[ "$line" =~ ^[[:space:]]*readOnly: ]]; then
                local ro=$(echo "$line" | sed 's/.*readOnly: *//' | sed 's/ *$//')
                echo "TARGET_READONLY=$ro"
            fi
        fi
    done < "$file"
    
    # Parse labels
    local in_labels=false
    while IFS= read -r line; do
        if [[ "$line" =~ ^labels: ]]; then
            in_labels=true
            continue
        fi
        
        if [[ "$in_labels" == "true" && "$line" =~ ^[a-zA-Z] ]]; then
            break
        fi
        
        if [[ "$in_labels" == "true" && "$line" =~ ^[[:space:]]+[a-zA-Z] ]]; then
            local key
            key=$(echo "$line" | sed 's/^ *//' | sed 's/: .*//')
            local value
            value=$(echo "$line" | sed 's/.*: *//' | sed 's/ *$//')
            # Combine key and value and safely single-quote the result so it can be eval'ed without code injection.
            local combined
            combined="${key}=${value}"
            # Escape any single quotes in the combined string for safe single-quoting in the shell.
            local escaped_combined
            escaped_combined=$(printf "%s" "$combined" | sed "s/'/'\"'\"'/g")
            echo "LABEL='$escaped_combined'"
        fi
    done < "$file"
}

# Validate namespace exists
validate_namespace() {
    local namespace="$1"
    if ! kubectl get namespace "$namespace" &> /dev/null; then
        log_error "Namespace '$namespace' does not exist"
        return 1
    fi
    log_verbose "Namespace '$namespace' exists"
    return 0
}

# Get source PVC and validate
get_source_pvc() {
    local pvc_name="$1"
    local namespace="$2"
    
    if ! kubectl get pvc "$pvc_name" -n "$namespace" &> /dev/null; then
        log_error "Source PVC '$pvc_name' not found in namespace '$namespace'"
        exit 1
    fi
    
    local phase
    phase=$(kubectl get pvc "$pvc_name" -n "$namespace" -o jsonpath='{.status.phase}')
    if [[ "$phase" != "Bound" ]]; then
        log_error "Source PVC '$pvc_name' is not bound (phase: $phase)"
        exit 1
    fi
    
    log_verbose "Source PVC is bound"
}

# Get PV bound to PVC
get_source_pv() {
    local pvc_name="$1"
    local namespace="$2"
    
    local pv_name
    pv_name=$(kubectl get pvc "$pvc_name" -n "$namespace" -o jsonpath='{.spec.volumeName}')
    
    if [[ -z "$pv_name" ]]; then
        log_error "Could not find PV bound to PVC '$pvc_name'"
        exit 1
    fi
    
    log_verbose "Source PV: $pv_name"
    echo "$pv_name"
}

# Validate VAST CSI driver
validate_vast_pv() {
    local pv_name="$1"
    
    local driver
    driver=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.csi.driver}')
    
    if [[ "$driver" != "$VAST_CSI_DRIVER" ]]; then
        log_error "PV '$pv_name' is not a VAST CSI volume (driver: $driver)"
        exit 1
    fi
    
    log_verbose "PV is VAST CSI volume"
}

# Extract volume handle
get_volume_handle() {
    local pv_name="$1"
    local handle
    handle=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.csi.volumeHandle}')
    
    if [[ -z "$handle" ]]; then
        log_error "Could not extract volumeHandle from PV '$pv_name'"
        exit 1
    fi
    
    log_verbose "Volume handle: $handle"
    echo "$handle"
}

# Get volume attributes (excluding csiProvisionerIdentity)
get_volume_attributes() {
    local pv_name="$1"
    
    local attributes
    attributes=$(kubectl get pv "$pv_name" -o go-template='{{range $k, $v := .spec.csi.volumeAttributes}}{{if ne $k "csiProvisionerIdentity"}}{{$k}}={{$v}},{{end}}{{end}}' 2>/dev/null | sed 's/,$//' || echo "")
    
    if [[ -z "$attributes" ]]; then
        log_verbose "No volumeAttributes found in PV '$pv_name'"
    else
        log_verbose "Volume attributes: $attributes"
    fi
    
    echo "$attributes"
}

# Get capacity
get_capacity() {
    local pv_name="$1"
    local capacity
    capacity=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.capacity.storage}')
    log_verbose "Capacity: $capacity"
    echo "$capacity"
}

# Generate target PV name
generate_pv_name() {
    local source_namespace="$1"
    local source_pvc="$2"
    local target_namespace="$3"
    echo "shared-${source_namespace}-${source_pvc}-${target_namespace}"
}

# Create PV YAML
create_pv_yaml() {
    local pv_name="$1"
    local volume_handle="$2"
    local volume_attributes="$3"
    local capacity="$4"
    local source_namespace="$5"
    local source_pvc="$6"
    local target_pvc="$7"
    local target_namespace="$8"
    local read_only="${9:-false}"
    local additional_labels="${10}"
    
    local attrs_yaml=""
    if [[ -n "$volume_attributes" ]]; then
        IFS=',' read -ra ATTRS <<< "$volume_attributes"
        for attr in "${ATTRS[@]}"; do
            IFS='=' read -r key value <<< "$attr"
            attrs_yaml+="      $key: \"$value\""$'\n'
        done
    fi
    
    local extra_labels=""
    if [[ -n "$additional_labels" ]]; then
        IFS=',' read -ra LABELS <<< "$additional_labels"
        for label in "${LABELS[@]}"; do
            IFS='=' read -r key value <<< "$label"
            extra_labels+="    $key: \"$value\""$'\n'
        done
    fi
    
    cat << EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ${pv_name}
  labels:
    coreweave.com/parent-pvc: ${source_pvc}
    coreweave.com/parent-namespace: ${source_namespace}
    coreweave.com/target-pvc: ${target_pvc}
    coreweave.com/target-namespace: ${target_namespace}
    coreweave.com/shared-by: dfs-shared-pvc-script
${extra_labels}spec:
  capacity:
    storage: ${capacity}
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ${STORAGE_CLASS}
  volumeMode: Filesystem
  csi:
    driver: ${VAST_CSI_DRIVER}
    volumeHandle: ${volume_handle}
    readOnly: ${read_only}
    volumeAttributes:
${attrs_yaml}
EOF
}

# Create PVC YAML
create_pvc_yaml() {
    local pvc_name="$1"
    local pv_name="$2"
    local capacity="$3"
    local namespace="$4"
    local source_namespace="$5"
    local source_pvc="$6"
    local additional_labels="$7"
    
    local extra_labels=""
    if [[ -n "$additional_labels" ]]; then
        IFS=',' read -ra LABELS <<< "$additional_labels"
        for label in "${LABELS[@]}"; do
            IFS='=' read -r key value <<< "$label"
            extra_labels+="    $key: \"$value\""$'\n'
        done
    fi
    
    cat << EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${pvc_name}
  namespace: ${namespace}
  labels:
    coreweave.com/parent-pvc: ${source_pvc}
    coreweave.com/parent-namespace: ${source_namespace}
    coreweave.com/shared-by: dfs-shared-pvc-script
${extra_labels}spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: ${capacity}
  storageClassName: ${STORAGE_CLASS}
  volumeName: ${pv_name}
  volumeMode: Filesystem
EOF
}

# Apply resource
apply_resource() {
    local yaml="$1"
    local description="$2"
    
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "DRY RUN - Would create $description:"
        echo "$yaml"
        echo "---"
        return 0
    else
        if echo "$yaml" | kubectl apply -f - &> /dev/null; then
            log_success "Created $description"
            return 0
        else
            log_error "Failed to create $description"
            echo "$yaml" >&2
            return 1
        fi
    fi
}

# Share PVC (core logic)
share_pvc() {
    local source_pvc="$1"
    local source_namespace="$2"
    local target_pvc="$3"
    local target_namespace="$4"
    local read_only="${5:-false}"
    local additional_labels="${6:-}"
    
    log_info "Sharing '$source_namespace/$source_pvc' to '$target_namespace/$target_pvc'"
    
    if ! validate_namespace "$target_namespace"; then
        exit 1
    fi
    
    if kubectl get pvc "$target_pvc" -n "$target_namespace" &> /dev/null; then
        log_warn "Target PVC '$target_pvc' already exists in '$target_namespace'"
        return 0
    fi
    
    local source_pv
    source_pv=$(get_source_pv "$source_pvc" "$source_namespace")
    
    validate_vast_pv "$source_pv"
    
    local volume_handle
    volume_handle=$(get_volume_handle "$source_pv")
    
    local volume_attributes
    volume_attributes=$(get_volume_attributes "$source_pv")
    
    local capacity
    capacity=$(get_capacity "$source_pv")
    
    local target_pv
    target_pv=$(generate_pv_name "$source_namespace" "$source_pvc" "$target_namespace")
    
    if kubectl get pv "$target_pv" &> /dev/null; then
        log_warn "Target PV '$target_pv' already exists"
    else
        local pv_yaml
        pv_yaml=$(create_pv_yaml "$target_pv" "$volume_handle" "$volume_attributes" \
            "$capacity" "$source_namespace" "$source_pvc" "$target_pvc" "$target_namespace" \
            "$read_only" "$additional_labels")
        
        apply_resource "$pv_yaml" "PV '$target_pv'"
    fi
    
    local pvc_yaml
    pvc_yaml=$(create_pvc_yaml "$target_pvc" "$target_pv" "$capacity" "$target_namespace" \
        "$source_namespace" "$source_pvc" "$additional_labels")
    
    apply_resource "$pvc_yaml" "PVC '$target_namespace/$target_pvc'"
}

# Command: apply
cmd_apply() {
    local source_pvc=""
    local source_namespace=""
    local target_pvcs=()
    local target_namespaces=()
    local target_read_only=()
    local manifest_file=""
    local additional_labels=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--source-pvc)
                source_pvc="$2"
                shift 2
                ;;
            -n|--source-namespace)
                source_namespace="$2"
                shift 2
                ;;
            -t|--target-pvc)
                target_pvcs+=("$2")
                target_read_only+=("false")
                shift 2
                ;;
            -N|--target-namespace)
                target_namespaces+=("$2")
                shift 2
                ;;
            -r|--read-only)
                if [[ ${#target_read_only[@]} -gt 0 ]]; then
                    target_read_only[$((${#target_read_only[@]} - 1))]="true"
                fi
                shift
                ;;
            -l|--label)
                if [[ -n "$additional_labels" ]]; then
                    additional_labels+=","
                fi
                additional_labels+="$2"
                shift 2
                ;;
            -f|--file)
                manifest_file="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                usage_apply
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_kubectl
    
    # Handle manifest file
    if [[ -n "$manifest_file" ]]; then
        log_info "Applying from manifest: $manifest_file"
        
        local parse_output
        parse_output=$(parse_manifest "$manifest_file")
        
        eval "$parse_output"
        
        if [[ -z "$SOURCE_PVC" || -z "$SOURCE_NAMESPACE" ]]; then
            log_error "Invalid manifest: missing source"
            exit 1
        fi
        
        source_pvc="$SOURCE_PVC"
        source_namespace="$SOURCE_NAMESPACE"
        
        # Collect targets from parsed output
        local current_pvc="" current_ns="" current_ro="false"
        while IFS= read -r line; do
            if [[ "$line" =~ ^TARGET_PVC= ]]; then
                current_pvc="${line#TARGET_PVC=}"
            elif [[ "$line" =~ ^TARGET_NAMESPACE= ]]; then
                current_ns="${line#TARGET_NAMESPACE=}"
            elif [[ "$line" =~ ^TARGET_READONLY= ]]; then
                current_ro="${line#TARGET_READONLY=}"
                if [[ -n "$current_pvc" && -n "$current_ns" ]]; then
                    target_pvcs+=("$current_pvc")
                    target_namespaces+=("$current_ns")
                    target_read_only+=("$current_ro")
                    current_pvc=""
                    current_ns=""
                    current_ro="false"
                fi
            fi
        done <<< "$parse_output"
        
        # Handle last target if no readOnly specified
        if [[ -n "$current_pvc" && -n "$current_ns" ]]; then
            target_pvcs+=("$current_pvc")
            target_namespaces+=("$current_ns")
            target_read_only+=("$current_ro")
        fi
        
        # Collect labels
        while IFS= read -r line; do
            if [[ "$line" =~ ^LABEL= ]]; then
                local label="${line#LABEL=}"
                if [[ -n "$additional_labels" ]]; then
                    additional_labels+=","
                fi
                additional_labels+="$label"
            fi
        done <<< "$parse_output"
    fi
    
    # Validate inputs
    if [[ -z "$source_pvc" || -z "$source_namespace" ]]; then
        log_error "Source PVC and namespace required"
        exit 1
    fi
    
    if [[ ${#target_pvcs[@]} -eq 0 ]]; then
        log_error "At least one target required"
        exit 1
    fi
    
    if [[ ${#target_pvcs[@]} -ne ${#target_namespaces[@]} ]]; then
        log_error "Each target PVC must have a corresponding namespace"
        exit 1
    fi
    
    validate_namespace "$source_namespace" || exit 1
    get_source_pvc "$source_pvc" "$source_namespace"
    
    log_info "Sharing to ${#target_pvcs[@]} target(s)"
    
    local failed=0
    for i in "${!target_pvcs[@]}"; do
        if ! share_pvc "$source_pvc" "$source_namespace" \
            "${target_pvcs[$i]}" "${target_namespaces[$i]}" \
            "${target_read_only[$i]}" "$additional_labels"; then
            ((failed++))
        fi
    done
    
    if [[ $failed -gt 0 ]]; then
        log_error "$failed target(s) failed"
        exit 1
    fi
    
    if [[ "${DRY_RUN:-false}" != "true" ]]; then
        log_success "All targets completed"
    else
        log_info "Dry run completed"
    fi
}

# Command: list
cmd_list() {
    local source_filter=""
    local target_filter=""
    local output_format="table"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --source)
                source_filter="$2"
                shift 2
                ;;
            --target)
                target_filter="$2"
                shift 2
                ;;
            --output)
                output_format="$2"
                shift 2
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                usage_list
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_kubectl
    
    # Build label selector
    local label_selector="$SCRIPT_LABEL"
    
    if [[ -n "$source_filter" ]]; then
        IFS='/' read -r ns pvc <<< "$source_filter"
        if [[ -n "$pvc" ]]; then
            label_selector+=",coreweave.com/parent-namespace=$ns,coreweave.com/parent-pvc=$pvc"
        fi
    fi
    
    if [[ -n "$target_filter" ]]; then
        label_selector+=",coreweave.com/target-namespace=$target_filter"
    fi
    
    # Get PVs
    local pvs
    pvs=$(kubectl get pv -l "$label_selector" -o json 2>/dev/null || echo '{"items":[]}')
    
    if [[ "$output_format" == "json" ]]; then
        echo "$pvs"
        return 0
    elif [[ "$output_format" == "yaml" ]]; then
        kubectl get pv -l "$label_selector" -o yaml 2>/dev/null
        return 0
    fi
    
    # Table output
    printf "%-45s %-20s %-20s %-15s %-10s\n" "PV NAME" "SOURCE" "TARGET" "STATUS" "READ-ONLY"
    printf "%-45s %-20s %-20s %-15s %-10s\n" "$(printf '%0.s-' {1..45})" "$(printf '%0.s-' {1..20})" "$(printf '%0.s-' {1..20})" "$(printf '%0.s-' {1..15})" "$(printf '%0.s-' {1..10})"
    
    kubectl get pv -l "$label_selector" -o custom-columns=\
NAME:.metadata.name,\
SOURCE_NS:.metadata.labels.coreweave\\.com/parent-namespace,\
SOURCE_PVC:.metadata.labels.coreweave\\.com/parent-pvc,\
TARGET_NS:.metadata.labels.coreweave\\.com/target-namespace,\
TARGET_PVC:.metadata.labels.coreweave\\.com/target-pvc,\
STATUS:.status.phase,\
READONLY:.spec.csi.readOnly 2>/dev/null | tail -n +2 | while read -r name src_ns src_pvc tgt_ns tgt_pvc status ro; do
        printf "%-45s %-20s %-20s %-15s %-10s\n" \
            "$name" \
            "$src_ns/$src_pvc" \
            "$tgt_ns/$tgt_pvc" \
            "${status:-N/A}" \
            "${ro:-false}"
    done
    
    echo ""
    local count
    count=$(kubectl get pv -l "$label_selector" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    echo "Total: $count shared PV(s)"
}

# Command: validate
cmd_validate() {
    local manifest_file=""
    local source_filter=""
    local check_drift=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--file)
                manifest_file="$2"
                shift 2
                ;;
            --source)
                source_filter="$2"
                shift 2
                ;;
            --check-drift)
                check_drift=true
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                usage_validate
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_kubectl
    
    if [[ -n "$manifest_file" ]]; then
        log_info "Validating manifest: $manifest_file"
        
        if [[ ! -f "$manifest_file" ]]; then
            log_error "File not found: $manifest_file"
            exit 1
        fi
        
        local parse_output
        if ! parse_output=$(parse_manifest "$manifest_file" 2>&1); then
            log_error "Failed to parse manifest"
            echo "$parse_output"
            exit 1
        fi
        
        eval "$parse_output"
        
        if [[ -z "$SOURCE_PVC" || -z "$SOURCE_NAMESPACE" ]]; then
            log_error "Manifest missing required source fields"
            exit 1
        fi
        
        log_success "Manifest syntax valid"
        
        # Validate source exists
        if kubectl get pvc "$SOURCE_PVC" -n "$SOURCE_NAMESPACE" &> /dev/null; then
            log_success "Source PVC exists: $SOURCE_NAMESPACE/$SOURCE_PVC"
        else
            log_warn "Source PVC not found: $SOURCE_NAMESPACE/$SOURCE_PVC"
        fi
        
        # Count targets
        local target_count=0
        while IFS= read -r line; do
            if [[ "$line" =~ ^TARGET_PVC= ]]; then
                ((target_count++))
            fi
        done <<< "$parse_output"
        
        log_info "Manifest defines $target_count target(s)"
    fi
    
    if [[ -n "$source_filter" ]]; then
        IFS='/' read -r ns pvc <<< "$source_filter"
        
        log_info "Validating source: $ns/$pvc"
        
        if ! kubectl get pvc "$pvc" -n "$ns" &> /dev/null; then
            log_error "Source PVC not found: $ns/$pvc"
            exit 1
        fi
        
        log_success "Source PVC exists"
        
        # List derived shares
        local count
        count=$(kubectl get pv -l "$SCRIPT_LABEL,coreweave.com/parent-namespace=$ns,coreweave.com/parent-pvc=$pvc" --no-headers 2>/dev/null | wc -l | tr -d ' ')
        
        log_info "Found $count derived share(s)"
        
        if [[ "$check_drift" == "true" ]]; then
            log_info "Checking for configuration drift..."
            
            local source_pv
            source_pv=$(get_source_pv "$pvc" "$ns")
            
            local source_handle
            source_handle=$(get_volume_handle "$source_pv")
            
            # Check each derived PV
            kubectl get pv -l "$SCRIPT_LABEL,coreweave.com/parent-namespace=$ns,coreweave.com/parent-pvc=$pvc" -o name 2>/dev/null | while read -r pv_name; do
                pv_name=${pv_name#persistentvolume/}
                
                local derived_handle
                derived_handle=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.csi.volumeHandle}')
                
                if [[ "$source_handle" == "$derived_handle" ]]; then
                    log_success "PV $pv_name: volume handle matches"
                else
                    log_warn "PV $pv_name: volume handle mismatch!"
                fi
            done
        fi
    fi
    
    log_success "Validation complete"
}

# Command: delete
cmd_delete() {
    local source_filter=""
    local target_filter=""
    local delete_all=false
    local force=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --source)
                source_filter="$2"
                shift 2
                ;;
            --target)
                target_filter="$2"
                shift 2
                ;;
            --all)
                delete_all=true
                shift
                ;;
            --force)
                force=true
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                usage_delete
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_kubectl
    
    if [[ -z "$source_filter" && -z "$target_filter" && "$delete_all" != "true" ]]; then
        log_error "Must specify --source, --target, or --all"
        exit 1
    fi
    
    # Build selectors
    local pv_selector="$SCRIPT_LABEL"
    local pvc_list=()
    
    if [[ -n "$source_filter" ]]; then
        IFS='/' read -r ns pvc <<< "$source_filter"
        if [[ -n "$pvc" ]]; then
            pv_selector+=",coreweave.com/parent-namespace=$ns,coreweave.com/parent-pvc=$pvc"
        fi
    fi
    
    if [[ -n "$target_filter" ]]; then
        IFS='/' read -r ns pvc <<< "$target_filter"
        if [[ -n "$pvc" ]]; then
            pv_selector+=",coreweave.com/target-namespace=$ns,coreweave.com/target-pvc=$pvc"
            pvc_list=("$ns/$pvc")
        fi
    fi
    
    # Get resources to delete
    local pvs
    pvs=$(kubectl get pv -l "$pv_selector" -o name 2>/dev/null)
    
    if [[ -z "$pvs" ]]; then
        log_info "No resources found to delete"
        return 0
    fi
    
    local pv_count
    pv_count=$(echo "$pvs" | wc -l | tr -d ' ')
    
    # Get associated PVCs if not already specified
    if [[ ${#pvc_list[@]} -eq 0 ]]; then
        while read -r pv_name; do
            pv_name=${pv_name#persistentvolume/}
            local tgt_ns tgt_pvc
            tgt_ns=$(kubectl get pv "$pv_name" -o jsonpath='{.metadata.labels.coreweave\.com/target-namespace}')
            tgt_pvc=$(kubectl get pv "$pv_name" -o jsonpath='{.metadata.labels.coreweave\.com/target-pvc}')
            if [[ -n "$tgt_ns" && -n "$tgt_pvc" ]]; then
                pvc_list+=("$tgt_ns/$tgt_pvc")
            fi
        done <<< "$pvs"
    fi
    
    echo "Resources to delete:"
    echo "  PVs: $pv_count"
    echo "  PVCs: ${#pvc_list[@]}"
    
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "DRY RUN - Would delete:"
        echo "$pvs"
        for pvc in "${pvc_list[@]}"; do
            echo "pvc/$pvc"
        done
        return 0
    fi
    
    # Confirm unless --force
    if [[ "$force" != "true" ]]; then
        echo -n "Proceed with deletion? (yes/no): "
        read -r response
        if [[ "$response" != "yes" ]]; then
            log_info "Deletion cancelled"
            return 0
        fi
    fi
    
    # Delete PVCs first
    local failed=0
    for pvc in "${pvc_list[@]}"; do
        IFS='/' read -r ns name <<< "$pvc"
        if kubectl get pvc "$name" -n "$ns" &> /dev/null; then
            if kubectl delete pvc "$name" -n "$ns" &> /dev/null; then
                log_success "Deleted PVC: $ns/$name"
            else
                log_error "Failed to delete PVC: $ns/$name"
                ((failed++))
            fi
        fi
    done
    
    # Delete PVs
    while read -r pv_name; do
        if kubectl delete "$pv_name" &> /dev/null; then
            log_success "Deleted $pv_name"
        else
            log_error "Failed to delete $pv_name"
            ((failed++))
        fi
    done <<< "$pvs"
    
    if [[ $failed -gt 0 ]]; then
        log_error "$failed resource(s) failed to delete"
        exit 1
    fi
    
    log_success "Deletion complete"
}

# Command: reconcile
cmd_reconcile() {
    local manifest_file=""
    local prune=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--file)
                manifest_file="$2"
                shift 2
                ;;
            --prune)
                prune=true
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                usage_reconcile
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    if [[ -z "$manifest_file" ]]; then
        log_error "Manifest file required (-f/--file)"
        exit 1
    fi
    
    check_kubectl
    
    log_info "Reconciling state with manifest: $manifest_file"
    
    # Parse manifest
    local parse_output
    parse_output=$(parse_manifest "$manifest_file")
    eval "$parse_output"
    
    # Get desired state
    local desired_targets=()
    local current_pvc="" current_ns=""
    while IFS= read -r line; do
        if [[ "$line" =~ ^TARGET_PVC= ]]; then
            current_pvc="${line#TARGET_PVC=}"
        elif [[ "$line" =~ ^TARGET_NAMESPACE= ]]; then
            current_ns="${line#TARGET_NAMESPACE=}"
            if [[ -n "$current_pvc" && -n "$current_ns" ]]; then
                desired_targets+=("$current_ns/$current_pvc")
                current_pvc=""
                current_ns=""
            fi
        fi
    done <<< "$parse_output"
    
    # Get actual state
    local actual_pvs
    actual_pvs=$(kubectl get pv -l "$SCRIPT_LABEL,coreweave.com/parent-namespace=$SOURCE_NAMESPACE,coreweave.com/parent-pvc=$SOURCE_PVC" -o name 2>/dev/null || echo "")
    
    local actual_targets=()
    if [[ -n "$actual_pvs" ]]; then
        while read -r pv_name; do
            pv_name=${pv_name#persistentvolume/}
            local tgt_ns tgt_pvc
            tgt_ns=$(kubectl get pv "$pv_name" -o jsonpath='{.metadata.labels.coreweave\.com/target-namespace}')
            tgt_pvc=$(kubectl get pv "$pv_name" -o jsonpath='{.metadata.labels.coreweave\.com/target-pvc}')
            if [[ -n "$tgt_ns" && -n "$tgt_pvc" ]]; then
                actual_targets+=("$tgt_ns/$tgt_pvc")
            fi
        done <<< "$actual_pvs"
    fi
    
    # Find missing (need to create)
    local missing=()
    for desired in "${desired_targets[@]}"; do
        local found=false
        for actual in "${actual_targets[@]}"; do
            if [[ "$desired" == "$actual" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" != "true" ]]; then
            missing+=("$desired")
        fi
    done
    
    # Find extra (need to delete if pruning)
    local extra=()
    if [[ "$prune" == "true" ]]; then
        for actual in "${actual_targets[@]}"; do
            local found=false
            for desired in "${desired_targets[@]}"; do
                if [[ "$actual" == "$desired" ]]; then
                    found=true
                    break
                fi
            done
            if [[ "$found" != "true" ]]; then
                extra+=("$actual")
            fi
        done
    fi
    
    echo "Reconciliation plan:"
    echo "  Desired targets: ${#desired_targets[@]}"
    echo "  Actual targets:  ${#actual_targets[@]}"
    echo "  Missing (create): ${#missing[@]}"
    echo "  Extra (delete):   ${#extra[@]}"
    
    if [[ ${#missing[@]} -eq 0 && ${#extra[@]} -eq 0 ]]; then
        log_success "State matches manifest, nothing to do"
        return 0
    fi
    
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        if [[ ${#missing[@]} -gt 0 ]]; then
            echo ""
            echo "Would create:"
            for target in "${missing[@]}"; do
                echo "  - $target"
            done
        fi
        
        if [[ ${#extra[@]} -gt 0 ]]; then
            echo ""
            echo "Would delete:"
            for target in "${extra[@]}"; do
                echo "  - $target"
            done
        fi
        
        log_info "Dry run complete"
        return 0
    fi
    
    # Create missing
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_info "Creating ${#missing[@]} missing target(s)"
        
        # Re-apply manifest to create missing targets
        cmd_apply -f "$manifest_file"
    fi
    
    # Delete extra
    if [[ ${#extra[@]} -gt 0 ]]; then
        log_info "Deleting ${#extra[@]} extra target(s)"
        
        for target in "${extra[@]}"; do
            cmd_delete --target "$target" --force
        done
    fi
    
    log_success "Reconciliation complete"
}

# Main dispatcher
main() {
    if [[ $# -eq 0 ]]; then
        usage_global
    fi
    
    local command="$1"
    shift
    
    case "$command" in
        apply)
            cmd_apply "$@"
            ;;
        list)
            cmd_list "$@"
            ;;
        validate)
            cmd_validate "$@"
            ;;
        delete)
            cmd_delete "$@"
            ;;
        reconcile)
            cmd_reconcile "$@"
            ;;
        help)
            if [[ $# -gt 0 ]]; then
                case "$1" in
                    apply) usage_apply ;;
                    list) usage_list ;;
                    validate) usage_validate ;;
                    delete) usage_delete ;;
                    reconcile) usage_reconcile ;;
                    *) usage_global ;;
                esac
            else
                usage_global
            fi
            ;;
        --version)
            echo "VAST PVC Sharing Script v${VERSION}"
            exit 0
            ;;
        -h|--help)
            usage_global
            ;;
        *)
            log_error "Unknown command: $command"
            usage_global
            ;;
    esac
}

main "$@"
