# collector.py
from kubernetes import client, config

# Load kubeconfig
config.load_kube_config()
v1 = client.CoreV1Api()

def get_pod_health():
    result = []
    pods = v1.list_pod_for_all_namespaces(watch=False)

    for pod in pods.items:
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace
        phase = pod.status.phase

        pod_report = {
            "pod": pod_name,
            "namespace": namespace,
            "phase": phase,
            "issues": []
        }

        # Phase issue
        if phase != "Running":
            pod_report["issues"].append(f"Phase issue: {phase}")

        # Container checks
        if pod.status.container_statuses:
            for c in pod.status.container_statuses:
                
                if c.state.waiting:
                    reason = c.state.waiting.reason
                    if reason:
                        pod_report["issues"].append(f"Waiting: {reason}")

                if c.state.terminated:
                    reason = c.state.terminated.reason
                    if reason:
                        pod_report["issues"].append(f"Terminated: {reason}")

                if not c.ready:
                    pod_report["issues"].append("Container not ready")

        result.append(pod_report)

    return result
