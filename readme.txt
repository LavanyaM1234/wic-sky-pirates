-> pod_health_checker.py goes to each pod, if not running, shows tht, nd also goes to each container
in the pod to check their status, this happens in frequency of 5 secs

->deployment_health.py goes to all deployment and checks If desired != ready → unhealthy
ex-test-dep (default) → desired=100, ready=54, available=54, updated=100
We need to increase the replicas too much to test this code's working

->we will use promethus(wil send PromSQL query) for getting the cpu and memory for the pods, each pod will have cpu ,memory
request and limits, since we cant transfer all the cpu nd memory data(redundancy), so we will
keep a threshold and Checks if CPU or memory usage exceeds 80% of their respective limits.
FOR THIS TO WORK WE NEED TO KEEP RUNNING FOR PROMETHUS
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring
