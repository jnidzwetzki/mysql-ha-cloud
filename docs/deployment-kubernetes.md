# Example - Using Kubernetes

To reproduce this example, you need a Kubernetes cluster with at least three worker nodes. The following services are deployed to the cluster:

* Three Consul instances, they are used for the election of the primary MySQL server, for service discovery, and for providing additional information about the state of the cluster.
* One of the MinIO object storage to store MySQL backups. These backups are used to bootstrap new MySQL replicas automatically. MinIO needs at least to provide four nodes / volumes to provide highly available. Therefore, a persistent iSCSI volume is used in this example. On this volume, you can also store a MySQL backup that is used to bootstrap the cluster. However, the persistent volume is not necessary. The solution also works without this volume. If the MinIO pod is started on another node, a new backup is created and uploaded automatically.
* One primary MySQL server (read/write) and two read-only MySQL replicas. 
* An instance of [ProxySQL](https://github.com/sysown/proxysql) is available on every MySQL-Server. ProxySQL is used to access the MySQL installations. Write requests (e.g., `INSERT` or `UPDATE`) are automatically send to the replication leader, and read requests (e.g., `SELECT`) are sent to the replication follower.

__Note:__ If you don't have a local Kubernetes installation, you can use [kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/) to setup such a cluster locally. In addition, you find a proper Ansible Playbook [here](https://github.com/jnidzwetzki/ansible-playbooks/tree/main/playbooks) to create such a cluster with `Docker` or `Container.io` as runtime.

### Step 1 - Check your Kubernetes installation

Execute the command `kubectl get nodes` to check the state of your Kubernetes cluster. 

```bash
$ kubectl get nodes
NAME               STATUS   ROLES    AGE    VERSION
debian10-k8s-vm1   Ready    master   3d3h   v1.19.4
debian10-k8s-vm2   Ready    <none>   3d3h   v1.19.4
debian10-k8s-vm3   Ready    <none>   3d2h   v1.19.4
debian10-k8s-vm4   Ready    <none>   24h    v1.19.4
```

In this example, the node `debian10-k8s-vm1` is the contol node for the cluster. The nodes `debian10-k8s-vm2`, `debian10-k8s-vm3`, `debian10-k8s-vm4` are the worker nodes of the cluster.

### Step 2 - Deploy the Services

Please download the [configuration](https://raw.githubusercontent.com/jnidzwetzki/mysql-ha-cloud/main/deployment/mysql-kubernetes-iscsi.yml) for Kubernetes and adjust the configuration according to your local settings. For example, when you use the persistent iSCSI volume, the iSCSI target settings need to be adjusted. 

```bash
$ curl https://raw.githubusercontent.com/jnidzwetzki/mysql-ha-cloud/main/deployment/mysql-kubernetes-iscsi.yml --output mysql-kubernetes-iscsi.yml
$ kubectl create -f mysql-kubernetes-iscsi.yml
secret/chap-secret created
deployment.apps/minio created
service/minio created
service/consul created
statefulset.apps/consul created
statefulset.apps/mysql created
service/mysql created
```

After the deployment is done, the available pods should look as follows:

```bash
$ kubectl get pods
NAME                     READY   STATUS              RESTARTS   AGE
consul-0                 1/1     Running             0          3h49m
consul-1                 1/1     Running             0          2m43s
consul-2                 1/1     Running             0          2m41s
minio-567b86887c-wlpdn   1/1     Running             0          3h49m
mysql-0                  1/1     Running             0          3h49m
mysql-1                  1/1     Running             0          88s
mysql-2                  1/1     Running             0          13s
```

In addition, the following services should be available:

```bash
$ kubectl get services
NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)                         AGE
consul       NodePort    10.108.236.59   <none>        8500:30014/TCP                  3h50m
minio        NodePort    10.100.165.38   <none>        9000:30013/TCP                  3h50m
mysql        NodePort    10.103.124.5    <none>        3306:30015/TCP,6032:30016/TCP   3h50m
```

Consul tries to bootstrap a new cluster in the background and the Consul agents on the MySQL pods also try to join this cluster. The status of the consul cluster could be checked with the following command:

```bash
$ kubectl exec consul-0 -- consul members
Node      Address           Status  Type    Build  Protocol  DC   Segment
consul-0  10.244.3.22:8301  alive   server  1.9.0  2         dc1  <all>
consul-1  10.244.1.28:8301  alive   server  1.9.0  2         dc1  <all>
consul-2  10.244.2.27:8301  alive   server  1.9.0  2         dc1  <all>
mysql-0   10.244.3.21:8301  alive   client  1.8.4  2         dc1  <default>
mysql-1   10.244.1.29:8301  alive   client  1.8.4  2         dc1  <default>
mysql-2   10.244.2.28:8301  alive   client  1.8.4  2         dc1  <default>
```

The output shows that the deployment of the three Consul servers was successful. Three Consul servers are deployed, and from the MySQL installations, three agents joined the cluster. 

### Step 3 - Check Deployment

After the deployment is done, you can check which MySQL nodes are avaialable and which node is the replication leader:

```bash
$ kubectl exec consul-0 -- consul kv get -recurse mcm/instances
mcm/instances/10.244.1.29:{"ip_address": "10.244.1.29", "server_id": 2, "mysql_version": "8.0.21"}
mcm/instances/10.244.2.28:{"ip_address": "10.244.2.28", "server_id": 3, "mysql_version": "8.0.21"}
mcm/instances/10.244.3.21:{"ip_address": "10.244.3.21", "server_id": 1, "mysql_version": "8.0.21"}

$ kubectl exec consul-0 -- consul kv get mcm/replication_leader
{"ip_address": "10.244.3.21"}
```

In the logfiles of the pod, you can see which pod is the MySQL replication leader and which pods are the replication follower. Besides, it can be seen which backend MySQL server are added to ProxySQL:

```bash
$ kubectl logs mysql-0
[...]
2020-12-07 19:01:27,482 INFO root Setting up replication (leader=10.244.3.21)
[...]
2020-12-07 19:02:47,501 INFO root MySQL backend has changed (old=['10.244.1.29', '10.244.3.21'], new=['10.244.1.29', '10.244.2.28', '10.244.3.21']), reconfiguring
2020-12-07 19:02:47,501 INFO root Removing all old backend MySQL Server
2020-12-07 19:02:47,503 INFO root Adding 10.244.1.29 as backend MySQL Server
2020-12-07 19:02:47,505 INFO root Adding 10.244.2.28 as backend MySQL Server
2020-12-07 19:02:47,506 INFO root Adding 10.244.3.21 as backend MySQL Server
```

In addition, you can list the available backups of the database:

```bash
$ kubectl exec mysql-0 -- mc ls backup/mysqlbackup
[2020-12-06 21:23:55 UTC] 1.6MiB mysql_backup_1607289823.6914027.tgz
[2020-12-07 19:00:21 UTC] 1.6MiB mysql_backup_1607367611.8148804.tgz
```

You can use also your browser to check the Consul installation and the MinIO setup:

* At the URL [http://Kubernetes-Node:30013](http://Kubernetes-Node:30013) is the MinIO webinterface available. Please use the value of the variables `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` from the deployment description for the login.
* At the URL [http://Kubernetes-Node:30014](http://Kubernetes-Node:30014) is the Consul webinterface available.

### Step 4 - Use the highly-available MySQL-Server

On port `30015/tcp` on all Kubernetes nodes, you can now reach the highly-available MySQL-Server. As user use `MYSQL_APPLICATION_USER` and the `MYSQL_APPLICATION_PASSWORD` from the docker-swarm file. 

For example: 

```bash
mysql -u mysql_user -pmysql_secret -h <Kubernetes-Node> -P30015
```

While you work on the MySQL-Shell you can restart the Kubernetes worker nodes. Kubernetes will restart the missing pods on other nodes and the MySQL orchestrator will reconfigure the replication setup in MySQL. The MySQL-Shell is usable all the time for read- and write-requests.
