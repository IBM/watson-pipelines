# Orchestration Pipelines Runtime on Remote Data Plane

To support deploying Orchestration Pipelines Runtime on a remote data plane, the Orchestration Pipelines operator needs to be deployed to the management namespace of the physical location associated with the remote data plane.

## Requirements

- Configure the [global pull secret](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=cluster-updating-global-image-pull-secret)

- Setup remote physical location following this guides: [Setting up a remote physical location for IBM Software Hub](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=installing-setting-up-remote-physical-location) until step with [Installing service-specific software on remote physical locations](https://www.ibm.com/docs/en/SSNFH6_5.1.x/hub/install/remote-location-services.html)

- Install DataStage on a remote physical location following this guide: [Installing DataStage on a remote physical location](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=software-installing-datastage-remote-physical-location)

- Create data plane which will be using remote physical location, created in the first step. Use this guide in order to create data plane: [Creating data planes to organize remote physical locations](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=location-creating-data-planes-organize-remote-physical-locations)

Note: If using a private registry, an [image content source policy](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=registry-configuring-image-content-source-policy) will need to be configured. [Image mirroring](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=registry-mirroring-images-directly-private-container) will also be needed if the Orchestration Pipelines images has not been mirrored to this private registry.

## Deploying the Orchestration Pipelines operator

To deploy the operator on your physical location, login to the remote cluster via `oc` with cluster-admin role and run the command below.

```bash
./deploy_operator.sh --namespace <management-namespace> --datastage_pvc <rdp-datastage-pvc-name> --storage_class <storage-class-name>
```

- `management-namespace`: namespace name that is marked as `REMOTE_PROJECT_MANAGEMENT` in the [Setting up environment variables for a remote physical location](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=location-setting-up-environment-variables) step,
- `rdp-datastage-pvc-name`: PVC name that is created along with Datastage service instance at step [Installing DataStage on a remote physical location](https://www.ibm.com/docs/en/SSNFH6_5.1.x/hub/install/remote-location-services.html). Name format is "<DATASTAGE_RDP_SERVICE_NAME>-ibm-datastage-px-storage-pvc"
- `storage-class-name`: storage class name that is marked as `REMOTE_STG_CLASS_FILE` in the [Setting up environment variables for a remote physical location](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=location-setting-up-environment-variables)

# Using Orchestration Pipelines Runtime in a Project

To use a Orchestration Pipeliens remote Runtime with a project, that runtime environment must be selected in the project. All resources needed at runtime are created on the Spoke cluster by deploy_operator.sh script. Second step is flag enablement at the primary/Hub cluster for orchestration pipelines custom resource.

Creating runtime environment:

1. From the project's `Manage` tab, select `Environments`
2. On the Environments page, select the `Templates` tab and click on `New template`
3. On the `New environment` dialog, select `Pipelines` as the type and select the remote environment for the hardware configuration.

Enable Orchestration Pipelines remote runtime on a primary cluster

You can run the commands in this task exactly as written if you use set up environment variables for the remote physical location in addition to the installation environment variables script. For instructions, see [Setting up environment variables for a remote physical location](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=location-setting-up-environment-variables).

1. Log the cpd-cli in to the Red Hat® OpenShift® Container Platform cluster at the primary cluster:
```
${REMOTE_CPDM_OC_LOGIN}
```
Remember: REMOTE_CPDM_OC_LOGIN is an alias for the cpd-cli manage login-to-ocp command when you are connecting to a remote cluster.

2. Update Orchestration Pipelines CR:
```
cpd-cli manage update-cr \
--components=ws_pipelines \
--cpd_instance_ns=${PROJECT_CPD_INST_OPERANDS} \
--patch='{\"enableTaskRunManager\":True}'
```
Orchestration Pipelines is upgraded when the update-cr command returns:
```
[SUCCESS]... The update-cr command ran successfully
```

