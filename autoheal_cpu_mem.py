import logging
from kubernetes import client

logging.basicConfig(level=logging.INFO)

CPU_THRESHOLD_RATIO = 0.60    
MEM_THRESHOLD_RATIO = 0.60     



def get_owner_deployment(pod):
    if not pod.metadata.owner_references:
        return None

    apps_v1 = client.AppsV1Api()

    for owner in pod.metadata.owner_references:
        if owner.kind == "ReplicaSet":
            rs = apps_v1.read_namespaced_replica_set(
                owner.name, pod.metadata.namespace
            )
            if rs.metadata.owner_references:
                for owner2 in rs.metadata.owner_references:
                    if owner2.kind == "Deployment":
                        return owner2.name
    return None



def scale_deployment(namespace, deployment):
    apps_v1 = client.AppsV1Api()
    try:
        dep = apps_v1.read_namespaced_deployment(deployment, namespace)
        current = dep.spec.replicas
        new = current + 1

        dep.spec.replicas = new
        apps_v1.patch_namespaced_deployment(deployment, namespace, dep)

        logging.warning(f"[CPU/MEM] Scaled {deployment}: {current} → {new}")
        return new
    except Exception as e:
        logging.error(f"Scaling failed for {deployment}: {e}")
        return None



def process_cpu_mem_alerts(cpu_mem_list):
  

    v1 = client.CoreV1Api()
    results = []

    for item in cpu_mem_list:
        pod_full = item["pod"]                
        namespace, pod_name = pod_full.split("/")

        cpu_usage = item.get("cpu_usage", 0)
        cpu_limit = item.get("cpu_limit", 1)
        mem_usage = item.get("mem_usage", 0)
        mem_limit = item.get("mem_limit", 1)

        cpu_ratio = cpu_usage / cpu_limit if cpu_limit > 0 else 0
        mem_ratio = mem_usage / mem_limit if mem_limit > 0 else 0

        logging.info(f"[CPU/MEM] Processing {pod_full}")
        logging.info(f"  CPU ratio: {cpu_ratio:.2f}, MEM ratio: {mem_ratio:.2f}")

        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
        except Exception as e:
            logging.error(f"Pod not found: {pod_full}: {e}")
            continue

        deployment = get_owner_deployment(pod)

        if not deployment:
            logging.warning(f"No deployment owner for {pod_full}")
            continue

        scaled = False

    
        if cpu_ratio >= CPU_THRESHOLD_RATIO:
            scale_deployment(namespace, deployment)
            scaled = True

      
        if mem_ratio >= MEM_THRESHOLD_RATIO:
            scale_deployment(namespace, deployment)
            scaled = True

        results.append({
            "pod": pod_full,
            "deployment": deployment,
            "cpu_ratio": cpu_ratio,
            "mem_ratio": mem_ratio,
            "scaled": scaled
        })

    return results
