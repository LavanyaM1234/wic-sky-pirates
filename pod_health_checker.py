from kubernetes import client, config
import time

# Load kubeconfig
config.load_kube_config()
v1 = client.CoreV1Api()

def check_pod_health():
    print("\n--- Checking Pod Health ---")
    pods = v1.list_pod_for_all_namespaces(watch=False)

    for pod in pods.items:
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace
        phase = pod.status.phase

        # 1️⃣ PHASE CHECK
        if phase != "Running":
            print(f"[PHASE ISSUE] {pod_name} ({namespace}) → {phase}")

        # 2️⃣ CONTAINER STATUS CHECKS
        if pod.status.container_statuses:
            for c in pod.status.container_statuses:

                # CrashLoopBackOff / ImagePullBackOff / ErrImagePull
                if c.state.waiting:
                    reason = c.state.waiting.reason
                    if reason:
                        print(f"[WAITING] {pod_name} → {reason}")

                # OOMKilled or other terminations
                if c.state.terminated:
                    reason = c.state.terminated.reason
                    if reason:
                        print(f"[TERMINATED] {pod_name} → {reason}")

                # Containers not ready
                if not c.ready:
                    print(f"[NOT READY] {pod_name} → container not ready")

while True:
    check_pod_health()
    time.sleep(5)
