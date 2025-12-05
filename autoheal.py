
import time
import logging
from typing import List, Dict, Any, Optional
import requests
from kubernetes import client, config

STATUS_ENDPOINT = "http://212.2.244.14:8000/pod"  
print("correct api")
POLL_INTERVAL = 3 
COOLDOWN = 10  
RESTART_THRESHOLD = 2  


WATCH_WAITING_REASONS = {
    "CrashLoopBackOff",
    "Error",
    "ImagePullBackOff",
}


WATCH_TERMINATED_REASONS = {
    "OOMKilled",
    "Error",
    "StartError",
}


PHASE_FAILURES = {"Failed"}
PHASE_NON_ACTION = {"Succeeded"} 


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


config.load_kube_config()  
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


last_deleted: Dict[str, float] = {}


def now() -> float:
    import time as _t
    return _t.time()

def within_cooldown(ns: str, name: str) -> bool:
    key = f"{ns}/{name}"
    ts = last_deleted.get(key, 0)
    return (now() - ts) < COOLDOWN

def mark_deleted(ns: str, name: str) -> None:
    key = f"{ns}/{name}"
    last_deleted[key] = now()

def delete_pod(name: str, namespace: str = "default") -> None:
    if within_cooldown(namespace, name):
        logging.info(f"Cooldown active for {namespace}/{name}, skipping delete.")
        return
    try:
        v1.delete_namespaced_pod(name=name, namespace=namespace)
        mark_deleted(namespace, name)
        logging.info(f"Deleted pod {namespace}/{name} to restart.")
    except client.exceptions.ApiException as e:
       
        logging.error(f"Failed to delete pod {namespace}/{name}: {e}")

def check_images_for_pod(namespace: str, pod_name: str) -> None:
    try:
        pod = v1.read_namespaced_pod(pod_name, namespace)
        for c in pod.spec.containers:
            logging.info(f"Pod {pod_name} container {c.name} uses image {c.image}")
    except client.exceptions.ApiException as e:
        logging.warning(f"Could not fetch pod spec for {namespace}/{pod_name}: {e}")

def autoscale_owning_deployment(namespace: str, pod_name: str) -> None:
    try:
        pod = v1.read_namespaced_pod(pod_name, namespace)
        owner_refs = pod.metadata.owner_references or []
        for ref in owner_refs:
            if ref.kind == "ReplicaSet":
                rs = apps_v1.read_namespaced_replica_set(ref.name, namespace)
                deploy_owner = rs.metadata.owner_references[0] if rs.metadata.owner_references else None
                if deploy_owner and deploy_owner.kind == "Deployment":
                    deploy_name = deploy_owner.name
                    deploy = apps_v1.read_namespaced_deployment(deploy_name, namespace)
                    new_replicas = (deploy.spec.replicas or 1) + 1
                    # Patch with minimal payload to avoid full object overwrite
                    patch_body = {"spec": {"replicas": new_replicas}}
                    apps_v1.patch_namespaced_deployment(deploy_name, namespace, patch_body)
                    logging.info(f"Scaled deployment {deploy_name} to {new_replicas} replicas")
                    return
    except client.exceptions.ApiException as e:
        logging.warning(f"Autoscale failed for {namespace}/{pod_name}: {e}")


def parse_issue_flags(issues: List[str]) -> Dict[str, Any]:
    
    flags = {
        "phase_issue": None,
        "waiting_reason": None,
        "terminated_reason": None,
        "container_not_ready": False,
        "has_failure": False,
    }

    for s in issues:
        if s.startswith("Phase issue:"):
            flags["phase_issue"] = s.split(":", 1)[1].strip()
        elif s.startswith("Waiting:"):
            flags["waiting_reason"] = s.split(":", 1)[1].strip()
        elif s.startswith("Terminated:"):
           
            flags["terminated_reason"] = s.split(":", 1)[1].strip()
        elif s.startswith("LastState Terminated:"):
           
            rhs = s.split(":", 1)[1].strip()
           
            if "StartError" in rhs:
                flags["terminated_reason"] = "StartError"
            elif "OOMKilled" in rhs:
                flags["terminated_reason"] = "OOMKilled"
            elif "Error" in rhs:
                flags["terminated_reason"] = "Error"
        elif s == "Container not ready":
            flags["container_not_ready"] = True

   
    if (flags["waiting_reason"] in WATCH_WAITING_REASONS) or (flags["terminated_reason"] in WATCH_TERMINATED_REASONS):
        flags["has_failure"] = True
    if flags["phase_issue"] in PHASE_FAILURES:
        flags["has_failure"] = True

    return flags

def should_delete_pod(flags: Dict[str, Any]) -> bool:
  
    phase = flags.get("phase_issue")
    waiting = flags.get("waiting_reason")
    terminated = flags.get("terminated_reason")
 
    if phase in PHASE_NON_ACTION:
        return False
    if waiting == "ContainerCreating":
        return False

    if waiting in WATCH_WAITING_REASONS:
        return True
    if terminated in WATCH_TERMINATED_REASONS:
        return True
    if phase in PHASE_FAILURES:
        return True

   
    return False

def maybe_autoscale(namespace: str, pod_name: str, flags: Dict[str, Any]) -> None:
    reasons_to_scale = {"CrashLoopBackOff", "OOMKilled", "RunContainerError", "ImagePullBackOff", "ErrImagePull", "StartError", "Error"}
    if flags.get("waiting_reason") in reasons_to_scale or flags.get("terminated_reason") in reasons_to_scale or flags.get("phase_issue") in PHASE_FAILURES:
        autoscale_owning_deployment(namespace, pod_name)


def fetch_status():
    try:
        resp = requests.get(STATUS_ENDPOINT, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            if "items" in data:
                return data["items"]
            if "pods" in data:
                return data["pods"]   # <-- FIX HERE

        return []

    except requests.RequestException as e:
        logging.error(f"Failed to fetch status from endpoint: {e}")
        return []

def process_item(item: Dict[str, Any]) -> None:
    pod_name = item.get("pod")
    namespace = item.get("namespace", "default")
    phase = item.get("phase")
    issues = item.get("issues", [])

    if not pod_name or not namespace:
        logging.warning(f"Skipping malformed item: {item}")
        return

    flags = parse_issue_flags(issues)

   
    summary_bits = []
    if flags["phase_issue"]:
        summary_bits.append(f"Phase {flags['phase_issue']}")
    if flags["waiting_reason"]:
        summary_bits.append(f"Waiting {flags['waiting_reason']}")
    if flags["terminated_reason"]:
        summary_bits.append(f"Terminated {flags['terminated_reason']}")
    if flags["container_not_ready"]:
        summary_bits.append("NotReady")
    summary = ", ".join(summary_bits) or phase

    logging.info(f"[{namespace}/{pod_name}] Status: {summary}")

 
    if should_delete_pod(flags):
        logging.warning(f"[{namespace}/{pod_name}] Healing action: delete + image check")
        delete_pod(pod_name, namespace)
        check_images_for_pod(namespace, pod_name)
        maybe_autoscale(namespace, pod_name, flags)
    else:
       
        if flags["container_not_ready"] or flags["phase_issue"] == "Pending" or flags["waiting_reason"] == "ContainerCreating":
            logging.debug(f"[{namespace}/{pod_name}] Observing transitional state, no delete.")

def main():
    logging.info("Starting autohealer (status endpoint-driven)...")
    while True:
        items = fetch_status()
        for item in items:
            
            process_item(item)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
