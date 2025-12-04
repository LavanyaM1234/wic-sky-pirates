import requests
from kubernetes import client, config

PROM_URL = "http://localhost:9090"
THRESHOLD_RATIO = 0.8

config.load_kube_config()
v1 = client.CoreV1Api()

def prom_query(query):
    try:
        r = requests.get(f"{PROM_URL}/api/v1/query", params={"query": query}, timeout=5)
        r.raise_for_status()
        resp = r.json()
        return resp.get('data', {}).get('result', [])
    except Exception as e:
        return []

def fetch_pod_cpu_mem():
    res = {}
    cpu_q = 'sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!=""}[1m]))'
    mem_q = 'sum by (namespace, pod) (container_memory_working_set_bytes{container!=""})'

    for item in prom_query(cpu_q):
        ns = item['metric'].get('namespace')
        pod = item['metric'].get('pod')
        cpu = float(item['value'][1])
        res[f"{ns}/{pod}"] = res.get(f"{ns}/{pod}", {})
        res[f"{ns}/{pod}"]["cpu_cores"] = cpu

    for item in prom_query(mem_q):
        ns = item['metric'].get('namespace')
        pod = item['metric'].get('pod')
        mem = float(item['value'][1])
        res[f"{ns}/{pod}"] = res.get(f"{ns}/{pod}", {})
        res[f"{ns}/{pod}"]["memory_bytes"] = mem

    return res

def fetch_pod_limits():
    limits = {}
    pods = v1.list_pod_for_all_namespaces().items
    for pod in pods:
        ns = pod.metadata.namespace
        pod_name = pod.metadata.name
        limits[f"{ns}/{pod_name}"] = {}
        for c in pod.spec.containers:
            cpu_limit = c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
            if cpu_limit:
                if "m" in cpu_limit:
                    cpu_limit = float(cpu_limit.replace("m", "")) / 1000
                else:
                    cpu_limit = float(cpu_limit)
            mem_limit = c.resources.limits.get("memory") if c.resources and c.resources.limits else None
            if mem_limit:
                if mem_limit.lower().endswith("mi"):
                    mem_limit = float(mem_limit[:-2]) * 1024 * 1024
                elif mem_limit.lower().endswith("gi"):
                    mem_limit = float(mem_limit[:-2]) * 1024 * 1024 * 1024
                else:
                    mem_limit = float(mem_limit)
            limits[f"{ns}/{pod_name}"]["cpu_limit"] = cpu_limit
            limits[f"{ns}/{pod_name}"]["mem_limit"] = mem_limit
    return limits

def get_anomalies():
    usage = fetch_pod_cpu_mem()
    limits = fetch_pod_limits()
    anomalies = []

    for pod, metrics in usage.items():
        cpu = metrics.get("cpu_cores", 0)
        mem = metrics.get("memory_bytes", 0)
        cpu_limit = limits.get(pod, {}).get("cpu_limit")
        mem_limit = limits.get(pod, {}).get("mem_limit")
        cpu_alert = cpu_limit and cpu / cpu_limit > THRESHOLD_RATIO
        mem_alert = mem_limit and mem / mem_limit > THRESHOLD_RATIO
        if cpu_alert or mem_alert:
            anomalies.append({
                "pod": pod,
                "cpu_usage": cpu,
                "cpu_limit": cpu_limit,
                "mem_usage": mem,
                "mem_limit": mem_limit,
                "cpu_alert": cpu_alert,
                "mem_alert": mem_alert
            })
    return anomalies
