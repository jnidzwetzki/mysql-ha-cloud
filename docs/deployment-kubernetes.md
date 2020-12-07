# Example - Using Kubernetes

To reproduce this example, you need a Kubernetes cluster with at lest three worker nodes. The following services are deployed to the cluster:

* Three Consul instances, they are used for election of the primary MySQL server, for service discovery, and for providing additional information about the state of the cluster.
* One of the MinIO object storage to store MySQL backups. These backups are used to bootstrap new MySQL replicas automatically. MinIO needs at least to provide four nodes / volumes to provide highly available. Therefore, a persistent iSCSI volume is used in this example. On this volume, you can also store a MySQL backup that is used to bootstrap the cluster. However, the persistent volume is not nesseary. The solution works also without this volume. If the minio pod is started on another node, a new backup is created and uploaded automatically.
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

Please download the [configuration](https://raw.githubusercontent.com/jnidzwetzki/mysql-ha-cloud/main/deployment/mysql-kubernetes-iscsi.yml) for Kubernetes and adjust the configuration according to you local settings. For example, when you use the persistent iSCSI volume, the target needs to be adjusted. 

```bash
$ curl https://raw.githubusercontent.com/jnidzwetzki/mysql-ha-cloud/main/deployment/mysql-kubernetes-iscsi.yml --output mysql-kubernetes-iscsi.yml
$ kubectl create -f mysql-kubernetes-iscsi.yml
```

### Step 3 - Check Deployment

### Step 4 - Use the highly-available MySQL-Server
