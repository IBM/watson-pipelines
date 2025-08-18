OPERATOR_REGISTRY="icr.io/cpopen"
OPERATOR_DIGEST="sha256:433e672036c51471f7666bb48dd0bfd9e11d6993b587fbfb79dd3eaac85944c9"
DATASTAGE_PVC=""
PHYSICAL_LOCATION_NAME=""
PHYSICAL_LOCATION_ID=""
WORKLOAD_NS=""
STORAGE_CLASS=""

kubernetesCLI="oc"

supportedVersions="5.1.1 5.1.2 5.1.3 5.2.0 5.2.1"
assetVersions="511 512 513 520"
imageDigests="sha256:433e672036c51471f7666bb48dd0bfd9e11d6993b587fbfb79dd3eaac85944c9 sha256:db31bf0f68ef94e187af781877492dc9e580f8540a5bf5a40b5b6d357a86a3e0 sha256:772f98763527c5452c662b2ae516de59c1f6edcf339da46231f4be8aab6c580d sha256:9dfb39ba9087cc23c6c25d2e536a310ebd40063f9e0bcc674e7445eb32b620fc sha256:433e672036c51471f7666bb48dd0bfd9e11d6993b587fbfb79dd3eaac85944c9"
version="5.1.1"

verify_args() {
  echo "---- verification of script arguments ----"
  # check if oc cli available
  which oc > /dev/null
  if [ $? -ne 0 ]; then
    echo "Unable to locate oc cli"
    exit 3
  fi
  
  # check if the specified namespace exists and is a management namespace
  oc get namespace $namespace &> /dev/null
  if [ $? -ne 0 ]; then
    echo "Namespace $namespace not found."
    exit 3
  fi
  oc -n $namespace get cm physical-location-info-cm &> /dev/null
  if [ $? -ne 0 ]; then
    echo "The specified namespace $namespace is not a management namespace. Unable to locate the configmap physical-location-info-cm."
    exit 3
  fi

  if [ -z $DATASTAGE_PVC ]; then
    oc -n $namespace get pvc $DATASTAGE_PVC &> /dev/null
    if [ $? -ne 0 ]; then
      echo "The specified DataStage $DATASTAGE_PVC is not in a management namespace, or does not exist."
      exit 3
    fi
  fi
}

check_version() {
  if [ -z $skipVersionCheck ]; then
    hub_url=`oc -n $namespace get cm physical-location-info-cm -o jsonpath='{.data.CPD_HUB_URL}'`
    if [ -z $hub_url ]; then
      echo "Unable to retrieve version from control plane. Defaulting version to ${version}".
      return 0
    fi
    asset_version=`curl -ks https://${hub_url}/data_intg/v3/assets/version`
    
    versionsArray=(${supportedVersions})
    assetVersionsArray=(${assetVersions})
    digestsArray=(${imageDigests})

    if [ ${#versionsArray[@]} -ne ${#assetVersionsArray[@]} ]; then
      echo "Mismatch size for '${supportedVersions}' and '${assetVersions}'"
      exit 1
    fi
    arraylength=${#versionsArray[@]}

    for (( i=0; i<${arraylength}; i++ ));
    do
      assetVersion="${assetVersionsArray[$i]}\.[0-9]+\.[0-9]+"
      echo "${asset_version}" | grep -E "${assetVersion}" &> /dev/null
      if [[ $? -eq 0 ]]; then
        version="${versionsArray[$i]}"
        OPERATOR_DIGEST="${digestsArray[$i]}"
        echo "Version determined from control plane: $version"
        echo "OPERATOR_DIGEST: ${OPERATOR_DIGEST}"
        break;
      fi 
    done
  else
    versionsArray=(${supportedVersions})
    digestsArray=(${imageDigests})
    arraylength=${#versionsArray[@]}
    for (( i=0; i<${arraylength}; i++ ));
    do
      ventry=${versionsArray[$i]}
      if [ "$ventry" == "$version" ]; then
        OPERATOR_DIGEST="${digestsArray[$i]}"
        echo "Version set by parameter: $version"
        echo "OPERATOR_DIGEST: ${OPERATOR_DIGEST}"
        break;
      fi
    done
  fi
}

read_location_info() {
  echo "---- read location info ----"
  PHYSICAL_LOCATION_NAME=$(oc get cm physical-location-info-cm -n $namespace -ojsonpath='{.data.PHYSICAL_LOCATION_NAME}')
  PHYSICAL_LOCATION_ID=$(oc get cm physical-location-info-cm -n $namespace -ojsonpath='{.data.PHYSICAL_LOCATION_ID}')
  if [[ -z $version ]]; then
    version=$(oc get cm physical-location-info-cm -n $namespace -ojsonpath='{.data.VERSION}')
  fi
  WORKLOAD_NS=$(oc get cm physical-location-info-cm -n $namespace -ojsonpath='{.data.WORKLOAD_NS}')
}

upgrade_orchestrationruntimes() {
  # upgrade pxruntime instaces to the same version
  instance_count=`oc -n $namespace get orchestrationruntime 2> /dev/null | wc -l | tr -d ' '`
  if [ $instance_count -gt 0 ]; then
    echo "Updating orchestrationruntime instances in $namespace to version ${version}"
    oc -n ${namespace} get orchestrationruntime 2> /dev/null | awk 'NR>1 { print $1 }' | xargs -I % oc -n ${namespace} patch orchestrationruntime % --type=merge -p "{\"spec\":{\"version\": \"${version}\"}}"
  fi
}

create_orchestration_runtime_crd() {
  echo "---- create runtime CRD ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  creationTimestamp: null
  name: orchestrationruntimes.wspipelines.cpd.ibm.com
spec:
  group: wspipelines.cpd.ibm.com
  names:
    kind: OrchestrationRuntime
    listKind: OrchestrationRuntimeList
    plural: orchestrationruntimes
    singular: orchestrationruntime
  scope: Namespaced
  versions:
  - additionalPrinterColumns:
      - description: The desired version of OrchestrationRuntime
        jsonPath: .spec.version
        name: Version
        type: string
      - description: The actual version OrchestrationRuntime
        jsonPath: .status.versions.reconciled
        name: Reconciled
        type: string
      - description: The status of OrchestrationRuntime
        jsonPath: .status.wspipelinesStatus
        name: Status
        type: string
      - description: The age of OrchestrationRuntime
        jsonPath: .metadata.creationTimestamp
        name: Age
        type: date
    name: v1
    schema:
      openAPIV3Schema:
        description: WSPipelines is the Schema for the wspipelines API
        properties:
          apiVersion:
            description: 'APIVersion defines the versioned schema of this representation of an object. Servers should convert recognized schemas to the latest internal value, and may reject unrecognized values. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#resources'
            type: string
          kind:
            description: 'Kind is a string value representing the REST resource this object represents. Servers may infer this from the endpoint the client submits requests to. Cannot be updated. In CamelCase. More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#types-kinds'
            type: string
          metadata:
            type: object
          spec:
            description: Spec defines the desired state of WSPipelines
            type: object
            x-kubernetes-preserve-unknown-fields: true
          status:
            description: Status defines the observed state of WSPipelines
            type: object
            x-kubernetes-preserve-unknown-fields: true
        type: object
    served: true
    storage: true
    subresources:
      status: {}
status:
  acceptedNames:
    kind: ""
    plural: ""
  conditions: null
  storedVersions: null
EOF
}

create_service_account() {
  echo "---- create Service Account ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ibm-cpd-orchestration-pipelines-operator-serviceaccount
  namespace: $namespace
  labels:
    app.kubernetes.io/instance: ibm-cpd-orchestration-pipelines-operator-sa
    app.kubernetes.io/managed-by: ibm-cpd-orchestration-pipelines-operator
    app.kubernetes.io/name: ibm-cpd-orchestration-pipelines-operator-sa
EOF
}

create_role() {
  echo "---- create Role ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ibm-cpd-orchestration-pipelines-operator-role
  namespace: $namespace
  labels:
     app.kubernetes.io/instance: ibm-cpd-orchestration-pipelines-operator-cluster-role
     app.kubernetes.io/managed-by: ibm-cpd-orchestration-pipelines-operator
     app.kubernetes.io/name: ibm-cpd-orchestration-pipelines-operator-cluster-role

rules:
- apiGroups:
  - ""
  - batch
  - extensions
  - apps
  - policy
  - rbac.authorization.k8s.io
  - autoscaling
  - route.openshift.io
  - authorization.openshift.io
  - networking.k8s.io
  resources:
  - secrets
  - pods
  - pods/exec
  - pods/log
  - jobs
  - configmaps
  - deployments
  - deployments/scale
  - statefulsets
  - statefulsets/scale
  - replicasets
  - services
  - persistentvolumeclaims
  - persistentvolumes
  - cronjobs
  - serviceaccounts
  - roles
  - rolebindings
  - horizontalpodautoscalers
  - jobs/status
  - pods/status
  - networkpolicies
  verbs:
  - apply
  - create
  - get
  - delete
  - watch
  - update
  - edit
  - list
  - patch
- apiGroups:
  - wspipelines.cpd.ibm.com
  resources:
  - OrchestrationRuntimes
  - OrchestrationRuntimes/status
  - OrchestrationRuntimes/finalizers
  - orchestrationruntimes/finalizers
  - orchestrationruntimes/status
  - orchestrationruntimes
  verbs:
  - apply
  - edit
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
EOF
}

create_role_binding() {
  echo "---- create Role Binding ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
kind: RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: ibm-cpd-orchestration-pipelines-operator-role-binding
  namespace: $namespace
  labels:
    app.kubernetes.io/instance: ibm-cpd-orchestration-pipelines-operator-role-binding
    app.kubernetes.io/managed-by: ibm-cpd-orchestration-pipelines-operator
    app.kubernetes.io/name: ibm-cpd-orchestration-pipelines-operator-role-binding
subjects:
- kind: ServiceAccount
  name: ibm-cpd-orchestration-pipelines-operator-serviceaccount
  namespace: $namespace
roleRef:
  kind: Role
  name: ibm-cpd-orchestration-pipelines-operator-role
  apiGroup: rbac.authorization.k8s.io
EOF
}

create_operator_deployment() {
  echo "---- remove previous operator deployment if exists ----"
  # remove deployment with incorrect name used previously
  $kubernetesCLI -n $namespace delete deploy ibm-cpd-orchestration-pipelines-operator --ignore-not-found=true
  echo "---- create operator deployment ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ibm-cpd-orchestration-pipelines-operator
  annotations:
    cloudpakName: IBM Orchestration Pipelines Cartridge for IBM Cloud Pak for Data
    productMetric: FREE
    productName: IBM Orchestration Pipelines for Cloud Pak for Data
    productVersion: $version
  labels:
    app.kubernetes.io/instance: ibm-cpd-orchestration-pipelines-operator
    app.kubernetes.io/managed-by: ibm-cpd-orchestration-pipelines-operator
    app.kubernetes.io/name: ibm-cpd-orchestration-pipelines-operator
    intent: projected
    icpdsupport/addOnId: ws-pipelines
    icpdsupport/app: operator
    name: ibm-cpd-orchestration-pipelines-operator
spec:
  selector:
    matchLabels:
      name: ibm-cpd-orchestration-pipelines-operator
  replicas: 1
  template:
    metadata:
      annotations:
        productMetric: FREE
        productName: IBM Orchestration Pipelines as a Service Anywhere
        productVersion: $version
      labels:
        app.kubernetes.io/instance: ibm-cpd-orchestration-pipelines-operator
        app.kubernetes.io/managed-by: ibm-cpd-orchestration-pipelines-operator
        app.kubernetes.io/name: ibm-cpd-orchestration-pipelines-operator
        intent: projected
        icpdsupport/addOnId: ws-pipelines
        icpdsupport/app: operator
        name: ibm-cpd-orchestration-pipelines-operator
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/arch
                    operator: In
                    values:
                      - amd64
      containers:
        - name: manager
          args:
            - "--zap-log-level"
            - "error"
            - "--max-concurrent-reconciles"
            - "6"
            - "--watches-file"
            - "./runtime-watch.yaml"
          image: ${OPERATOR_REGISTRY}/ibm-cpd-wspipelines-operator@${OPERATOR_DIGEST}
          imagePullPolicy: IfNotPresent
          livenessProbe:
            httpGet:
              path: /healthz
              port: 6789
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: /readyz
              port: 6789
            initialDelaySeconds: 5
            periodSeconds: 10
          securityContext:
            privileged: false
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false
            capabilities:
              drop:
                - ALL
          env:
            - name: WATCH_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: OPERATOR_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
              ephemeral-storage: 250Mi
            limits:
              cpu: 1
              memory: 1024Mi
              ephemeral-storage: 900Mi
      serviceAccount: ibm-cpd-orchestration-pipelines-operator-serviceaccount
      serviceAccountName: ibm-cpd-orchestration-pipelines-operator-serviceaccount
      terminationGracePeriodSeconds: 10
EOF
}

create_cr_role() {
  echo "---- create cr role ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  labels:
    icpdata_tether_resource: "true"
  name: ws-pipelines-cr-role
rules:
- apiGroups:
  - wspipelines.cpd.ibm.com
  resources:
  - orchestrationruntimes
  - orchestrationruntimes/status
  - orchestrationruntimes/finalizers
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
EOF
}

create_cr_role_binging() {
  echo "---- create cr Role Binding ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  labels:
    icpdata_tether_resource: "true"
  name: ws-pipelines-cr-rb
roleRef:
  kind: Role
  name: ws-pipelines-cr-role
  apiGroup: rbac.authorization.k8s.io
subjects:
- kind: ServiceAccount
  name: ibm-zen-agent-sa
  namespace: $namespace
EOF
}


create_cr_deployment() {
  echo "---- create CR deployment ----"
  cat <<EOF | $kubernetesCLI -n $namespace apply ${dryRun} -f -
apiVersion: wspipelines.cpd.ibm.com/v1
kind: OrchestrationRuntime
metadata:
  finalizers:
  - wspipelines.cpd.ibm.com/finalizer
  generation: 1
  name: remote-pipelines-$PHYSICAL_LOCATION_NAME
  namespace: $namespace
spec:
  description: ""
  ephemeralStorageLimit: 10Gi
  license:
    accept: true
  parameters:
    scaleConfig: small
    storageClass: $STORAGE_CLASS
    storageSize: "10"
  remote_dataplane: true
  version: $version
  zenMgmtNamespace: $namespace
  zenPhysicalLocationId: $PHYSICAL_LOCATION_ID
  zenPhysicalLocationName: $PHYSICAL_LOCATION_NAME
  zenServiceInstanceNamespace: $namespace
  zenWorkloadNamespace: $WORKLOAD_NS
  dsRuntimePVCName: $DATASTAGE_PVC
EOF
}

handle_badusage() {
  echo ""
  echo "Usage: $0 --namespace <management-namespace> --storage_class <storage-class-name> --datastage_pvc <pvc-name> [--version <version>]"
  echo "--namespace: the management namespace to deploy the Orchestration Pipelines operator into"
  echo "--version: the version of the operator to deploy. The following versions are supported: ${supportedVersions}"
  echo "--storage_class: name of the storage class which will be used by the runtime-resources. It must be same as datastage_pvc: $DATASTAGE_PVC storage class."
  echo "--datastage_pvc: name of the PVC used by datastage runtime deployment."
  echo ""
  exit 3
}

while [ $# -gt 0 ]
do
    case $1 in
        --namespace|-n)
            shift
            namespace="${1}"
            ;;
        --digest)
            shift
            OPERATOR_DIGEST="${1}"
            ;;
        --version)
            shift
            version="${1}"
            skipVersionCheck="true"
            ;;
        --datastage_pvc)
            shift
            DATASTAGE_PVC="${1}"
            ;;
        --storage_class)
            shift
            STORAGE_CLASS="${1}"
            ;;
        *)
            echo "Unknown parameter '${1}'"
            handle_badusage
            ;;
    esac
    if [ $# -gt 0 ]
    then
        shift
    fi
done

if [[ -z $namespace || -z $DATASTAGE_PVC || -z $STORAGE_CLASS ]]; then
  handle_badusage
fi

verify_args
check_version
read_location_info
create_orchestration_runtime_crd
create_service_account
create_role
create_role_binding
create_operator_deployment
create_cr_role
create_cr_role_binging
create_cr_deployment
upgrade_orchestrationruntimes
