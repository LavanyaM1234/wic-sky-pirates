-> pod_health_checker.py goes to each pod, if not running, shows tht, nd also goes to each container
in the pod to check their status, this happens in frequency of 5 secs
->deployment_health.py goes to all deployment and checks If desired != ready → unhealthy