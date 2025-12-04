from kubernetes import client, config

# Load kubeconfig
config.load_kube_config()
apps_v1 = client.AppsV1Api()

def get_deployment_health():
    result = []
    try:
        deployments = apps_v1.list_deployment_for_all_namespaces()
    except Exception as e:
        return {"error": f"Unable to fetch deployments: {e}"}

    for dep in deployments.items:
        name = dep.metadata.name
        namespace = dep.metadata.namespace
        desired = dep.spec.replicas or 0
        available = dep.status.available_replicas or 0
        ready = dep.status.ready_replicas or 0
        updated = dep.status.updated_replicas or 0

        dep_report = {
            "deployment": name,
            "namespace": namespace,
            "desired": desired,
            "ready": ready,
            "available": available,
            "updated": updated,
            "status": "HEALTHY" if ready >= desired else "UNHEALTHY"
        }

        result.append(dep_report)

    return result
