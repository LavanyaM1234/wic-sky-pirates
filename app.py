from fastapi import FastAPI
from collector import get_pod_health
from check_deployments import get_deployment_health
from cpu_memory_alerts import get_anomalies

app = FastAPI()

@app.get("/health")
def health():
    return {
        "pods": get_pod_health(),
        "deployments": get_deployment_health(),
        "anomalies": get_anomalies()
    }
