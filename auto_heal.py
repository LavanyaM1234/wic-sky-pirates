import logging
from typing import Dict, Any
from kubernetes import client, config
from autoheal_cpu_mem import process_cpu_mem_alerts

try:
    config.load_incluster_config()
    print("Running inside Kubernetes cluster")
except:
    config.load_kube_config()
    print("Running locally using kubeconfig")

CORE = client.CoreV1Api()
APPS = client.AppsV1Api()
AUTOSCALE = client.AutoscalingV2Api()



WATCH_TERMINATED = ["OOMKilled", "Error"]
WATCH_WAITING = ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]
PHASE_FAIL = ["Failed", "Unknown"]

CUSTOM_ISSUES = {
    "too many restarts": "TooManyRestarts",
    "increase memory limit": "OutOfMemory",
    "backoff": "BackOff"
}



def parse_issue_flags(issues):
    flags = {
        "phase_issue": None,
        "waiting_reason": None,
        "terminated_reason": None,
        "custom": None
    }

    for issue in issues:
        lower = issue.lower()

        
        for key, value in CUSTOM_ISSUES.items():
            if key in lower:
                flags["custom"] = value

      
        for w in WATCH_WAITING:
            if w.lower() in lower:
                flags["waiting_reason"] = w

       
        for t in WATCH_TERMINATED:
            if t.lower() in lower:
                flags["terminated_reason"] = t

    return flags


# ------------------------------
# Decide if pod must be deleted
# ------------------------------
def should_delete(flags):
    return any([
        flags["waiting_reason"],
        flags["terminated_reason"],
        flags["custom"],
        flags["phase_issue"]
    ])


# ------------------------------
# Delete Pod
# ------------------------------
def delete_pod(pod, ns):
    try:
        CORE.delete_namespaced_pod(pod, ns)
        logging.warning(f"Deleted pod: {ns}/{pod}")
        return True
    except Exception as e:
        logging.error(f"Delete failed {ns}/{pod}: {e}")
        return False


# ------------------------------
# Check images (placeholder)
# ------------------------------
def check_images_for_pod(ns, pod):
    logging.info(f"Image check for {ns}/{pod}")
    return True


# ------------------------------
# HPA Check
# ------------------------------
def has_hpa(namespace, deployment):
    try:
        hpas = AUTOSCALE.list_namespaced_horizontal_pod_autoscaler(namespace)
        for h in hpas.items:
            if h.spec.scale_target_ref.name == deployment:
                return True
    except:
        pass
    return False


# ------------------------------
# Manual Autoscaling (fallback)
# ------------------------------
def manual_autoscale(namespace, deployment, increase=True):
    try:
        dep = APPS.read_namespaced_deployment(deployment, namespace)
        current = dep.spec.replicas

        new_replicas = current + 1 if increase else max(1, current - 1)
        dep.spec.replicas = new_replicas

        APPS.patch_namespaced_deployment(deployment, namespace, dep)
        logging.warning(f"Scaled {deployment}: {current} → {new_replicas}")
        return new_replicas

    except Exception as e:
        logging.error(f"Manual autoscale failed: {e}")
        return None


# ------------------------------
# Autosc ale Logic
# ------------------------------
def maybe_autoscale(namespace, pod_name, flags):

    # Identify deployment from pod name prefix
    # (pod example: app-name-5987dfc77d-4sgx2)
    deployment = "-".join(pod_name.split("-")[:-2])

    if not deployment:
        logging.error(f"Cannot identify deployment for pod: {pod_name}")
        return "deployment_not_found"

    # If HPA exists, DO NOT manually scale
    if has_hpa(namespace, deployment):
        logging.info(f"HPA exists for {deployment}. Skipping manual scaling.")
        return "hpa_present"

    # If custom or waiting issues → scale up
    if flags["custom"] or flags["waiting_reason"]:
        new = manual_autoscale(namespace, deployment, increase=True)
        return {"scaled": "up", "replicas": new}

    # If terminated due to OOM → scale DOWN? Or up? (custom choice)
    if flags["terminated_reason"] == "OOMKilled":
        new = manual_autoscale(namespace, deployment, increase=True)
        return {"scaled": "up", "replicas": new}

    return "no_action"


# ------------------------------
# AUTO-HEAL ENTRYPOINT (POST)
# ------------------------------
def auto_heal(item: Dict[str, Any]):
    if "cpu_usage" in item and "mem_usage" in item:
        logging.warning("[AUTOHEAL] CPU/MEM event detected, forwarding to processor...")
        cpu_mem_result = process_cpu_mem_alerts([item])
        return {
            "status": "cpu_mem_processed",
            "result": cpu_mem_result
        }

    pod = item["pod"]
    ns = item.get("namespace", "default")
    issues = item.get("issues", [])
    phase = item.get("phase")

    flags = parse_issue_flags(issues)

    logging.warning(f"[AUTOHEAL] START for {ns}/{pod}")
    logging.warning(f"Flags: {flags}")

    if not should_delete(flags):
        logging.info(f"[AUTOHEAL] No issues found for {pod}. Skipping.")
        return {"status": "no_action"}

    # Delete pod
    delete_pod(pod, ns)

    # Image check
    check_images_for_pod(ns, pod)

    # Autoscaling
    scale_result = maybe_autoscale(ns, pod, flags)

    logging.warning(f"[AUTOHEAL] Completed for {pod}")

    return {
        "pod": pod,
        "flags": flags,
        "autoscale": scale_result,
        "status": "healed"
    }
