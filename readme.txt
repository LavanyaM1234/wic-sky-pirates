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

-> i need to see service communication part as well, need to research abt 502,503

->for fastapi to work remotely, we need to create a new vm(fastapi-vm)
1)need to create firewall rule to allow ssh nd port 8000 for fastapi
2)below command to create a vm, need to create a ssh first
civo instance create fastapi-vm `
  --region nyc1 `
  --size g4s.medium `
  --diskimage ubuntu-jammy `
  --publicip create `
  --firewall fastapi-fw `
  --initialuser root `
  --sshkey fastapi-key `
  --wait

3)ssh -i $HOME\.ssh\id_ed25519 root@<VM_PUBLIC_IP> //this is to log in to the vm
4)apt update -y
apt upgrade -y
apt install -y python3 python3-pip python3-venv
mkdir /app
cd /app
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn kubernetes pydantic
create a app folder nd paste health checker nd app.py code
vm need access to the kubeconfig file
run nohup for prometheus also
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > fastapi.log 2>&1 &
(the above thing to keep running evn if the ssh ended)

5) now in frontend to get these data 
http://212.2.244.14:8000/pod

http://212.2.244.14:8000/deployment

http://212.2.244.14:8000/anomalies
