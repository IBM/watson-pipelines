# Orchestration Pipelines Runtime on Remote Data Plane

To support deploying Orchestration Pipelines Runtime on a remote data plane, the Orchestration Pipelines operator needs to be deployed to the management namespace of the physical location associated with the remote data plane.

## Requirements

- Deploy the physical location and associate it with a [remote data plane](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=installing-setting-up-remote-physical-location)

- Configure the [global pull secret](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=cluster-updating-global-image-pull-secret)

Note: If using a private registry, an [image content source policy](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=registry-configuring-image-content-source-policy) will need to be configured. [Image mirroring](https://www.ibm.com/docs/en/software-hub/5.1.x?topic=registry-mirroring-images-directly-private-container) will also be needed if the Orchestration Pipelines images has not been mirrored to this private registry.

## Deploying the Orchestration Pipelines operator

To deploy the operator on your physical location, login to the remote cluster via `oc` with cluster-admin role and run the command below.

```bash
./deploy_operator.sh --namespace <management-namespace> --datastage_pvc <rdp-datastage-pvc-name> --storage_class <storage-class-name>
```

# Using Orchestration Pipelines Runtime in a Project

To use a Orchestration Pipeliens remote Runtime with a project, that runtime environment must be selected in the project. All resources needed at runtime are created on the Spoke cluster by deploy_operator.sh script.

Creating runtime environment:

1. From the project's `Manage` tab, select `Environments`
2. On the Environments page, select the `Templates` tab and click on `New template`
3. On the `New environment` dialog, select `Pipelines` as the type and select the remote environment for the hardware configuration.
