from kubernetes import client,config
import time

config.load_kube_config()

def check_deployments():
    apps_v1 = client.AppsV1Api()

    print("\n--- Checking Deployment Health ---")

    try:
        deployments = apps_v1.list_deployment_for_all_namespaces()
    except Exception as e:
        print(f"[ERROR] Unable to fetch deployments: {e}")
        return

    for dep in deployments.items:
        name = dep.metadata.name
        namespace = dep.metadata.namespace

        desired = dep.spec.replicas or 0
        available = dep.status.available_replicas or 0
        ready = dep.status.ready_replicas or 0
        updated = dep.status.updated_replicas or 0

        # If desired != ready → unhealthy
        if ready < desired:
            print(f"[UNHEALTHY] {name} ({namespace}) → "
                  f"desired={desired}, ready={ready}, available={available}, updated={updated}")
        else:
            print(f"[HEALTHY] {name} ({namespace}) → all replicas ready")

while True:
    check_deployments()
    time.sleep(5)