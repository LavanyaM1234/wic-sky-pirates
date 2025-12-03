# cpu_memory_alerts.py
import requests
from kubernetes import client, config
from urllib.parse import quote_plus

PROM_URL = "http://localhost:9090"
THRESHOLD_RATIO = 0.8  # Alert if usage > 80% of limit

# Load kubeconfig
config.load_kube_config()
v1 = client.CoreV1Api()

def prom_query(query):
    try:
        r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": query}, timeout=5)
        r.raise_for_status()
        resp = r.json()
        return resp.get('data', {}).get('result', [])
    except Exception as e:
        print("[ERROR] Prometheus request failed:", e)
        return []

def fetch_pod_cpu_mem():
    res = {}
    cpu_q = 'sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!=""}[1m]))'
    mem_q = 'sum by (namespace, pod) (container_memory_working_set_bytes{container!=""})'

    cpu_results = prom_query(cpu_q)
    mem_results = prom_query(mem_q)

    for item in cpu_results:
        ns = item['metric'].get('namespace')
        pod = item['metric'].get('pod')
        cpu = float(item['value'][1])
        res[f"{ns}/{pod}"] = res.get(f"{ns}/{pod}", {})
        res[f"{ns}/{pod}"]["cpu_cores"] = cpu

    for item in mem_results:
        ns = item['metric'].get('namespace')
        pod = item['metric'].get('pod')
        mem = float(item['value'][1])
        res[f"{ns}/{pod}"] = res.get(f"{ns}/{pod}", {})
        res[f"{ns}/{pod}"]["memory_bytes"] = mem

    return res

def fetch_pod_limits():
    """
    Fetch CPU/memory limits for all pods
    """
    limits = {}
    pods = v1.list_pod_for_all_namespaces().items
    for pod in pods:
        ns = pod.metadata.namespace
        pod_name = pod.metadata.name
        limits[f"{ns}/{pod_name}"] = {}
        for c in pod.spec.containers:
            # CPU limits in cores
            cpu_limit = c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
            if cpu_limit:
                if "m" in cpu_limit:  # milliCPU
                    cpu_limit = float(cpu_limit.replace("m", "")) / 1000
                else:
                    cpu_limit = float(cpu_limit)
            else:
                cpu_limit = None  # No limit set

            # Memory limits in bytes
            mem_limit = c.resources.limits.get("memory") if c.resources and c.resources.limits else None
            if mem_limit:
                if mem_limit.lower().endswith("mi"):
                    mem_limit = float(mem_limit[:-2]) * 1024 * 1024
                elif mem_limit.lower().endswith("gi"):
                    mem_limit = float(mem_limit[:-2]) * 1024 * 1024 * 1024
                else:
                    mem_limit = float(mem_limit)
            else:
                mem_limit = None  # No limit set

            limits[f"{ns}/{pod_name}"]["cpu_limit"] = cpu_limit
            limits[f"{ns}/{pod_name}"]["mem_limit"] = mem_limit
    return limits

def check_anomalies():
    usage = fetch_pod_cpu_mem()
    limits = fetch_pod_limits()

    print("\n=== Pods exceeding 80% of CPU/Memory limit ===")
    for pod, metrics in usage.items():
        cpu_usage = metrics.get("cpu_cores", 0)
        mem_usage = metrics.get("memory_bytes", 0)

        cpu_limit = limits.get(pod, {}).get("cpu_limit")
        mem_limit = limits.get(pod, {}).get("mem_limit")

        cpu_alert = cpu_limit and cpu_usage / cpu_limit > THRESHOLD_RATIO
        mem_alert = mem_limit and mem_usage / mem_limit > THRESHOLD_RATIO

        if cpu_alert or mem_alert:
            print(f"[ALERT] {pod}: ", end="")
            if cpu_alert:
                print(f"CPU usage {cpu_usage:.3f} cores / limit {cpu_limit} → {cpu_usage/cpu_limit:.0%} used; ", end="")
            if mem_alert:
                print(f"Memory usage {mem_usage/1024/1024:.1f}Mi / limit {mem_limit/1024/1024:.1f}Mi → {mem_usage/mem_limit:.0%} used", end="")
            print("")

if __name__ == "__main__":
    check_anomalies()
