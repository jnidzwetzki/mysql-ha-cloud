# MySQL highly-available cloud container orchestrator
<a href="https://travis-ci.org/jnidzwetzki/mysql-ha-cloud">
  <img alt="Build Status" src="https://travis-ci.org/jnidzwetzki/mysql-ha-cloud.svg?branch=main">
</a>
<a href="http://makeapullrequest.com">
 <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" />
</a><a href="https://gitter.im/mysql-ha-cloud/Lobby?utm_source=share-link&utm_medium=link&utm_campaign=share-link">
  <img alt="Join the chat at https://gitter.im/mysql-ha-cloud/Lobby" src="https://badges.gitter.im/Join%20Chat.svg">
</a><a href="https://hub.docker.com/repository/docker/jnidzwetzki/mysql-ha-cloud"><img src="https://img.shields.io/docker/stars/jnidzwetzki/mysql-ha-cloud.svg">
 </a>

<br>
This project provides containers and blueprints for robust, scalable, and highly-available MySQL installations. 
<br>
<br>


**Project state:** Alpha version in development

## Why do I need this?

In today's software development, robust applications are often developed as stateless cloud-native containers. Such containers can be easily moved between hosts, automatically restarted on failures, and replicated to handle increasing workloads. On the other hand, data are stored in relational database systems (RDBMS), which are often running on bare-metal hardware. Relational databases are stateful applications that are hard to scale, and they are often a single point of failure; high availability (HA) is rarely implemented.

## Are NoSQL databases a solution?

NoSQL databases are mostly cloud-native applications; however, they leak of the support of a full flagged relational database. Features such as transactions, complex data models, or consistency are omitted to make these systems horizontal scalable and fault-tolerant. However, simple tasks that can easily be implemented by using a relational database (e.g., an increasing counter, secondary indexes, isolation of uncommitted data, or joins) can be hard to implement. Therefore, relational databases are still used by moderns applications. 

## Are there other solutions?

Of course, there are other projects that also focus on highly available MySQL systems. For instance:

* [MySQL replication](https://dev.mysql.com/doc/refman/8.0/en/replication.html)
* [Galera cluster for MySQL](https://galeracluster.com/products/)
* [MySQL InnoDB Cluster](https://dev.mysql.com/doc/refman/8.0/en/admin-api-userguide.html)
* [Signal 18 replication manager](https://signal18.io/products/srm)
* [Autopilot pattern for MySQL](https://github.com/autopilotpattern/mysql)

## What is the main focus of this project?

This project will provide robust, tested, and easy to deploy containers for self-hosted MySQL cloud installations. The goal is that everybody can deploy highly-available and scalable MySQL installations and eliminate the DBMS as a single point of failure in his architecture.

## Example - Using Docker Swarm

In this example, a cluster consisting of four nodes running Debian 10 is used. The following services are deployed on the cluster:

* Three Consul instances, they are used for election of the primary MySQL server, for service discovery, and for providing additional information about the state of the cluster.
* One of the MinIO object storage to store MySQL backups. These backups are used to bootstrap new MySQL replicas automatically. MinIO needs at least to provide four nodes / volumes to provide highly available. In addition, deploying such a setup without labeling the Docker nodes and creating stateful volumes is hard. The data on the S§ Bucket are re-written periodically. Therefore, we don't deploy a highly available and replicated version of MinIO in this example.
* One primary MySQL server (read/write) and two read-only MySQL replicas. 

The four Docker nodes should be running in different availability zones. Therefore, one Docker node or availability zones can fail, and the MySQL service is still available. 

When one Docker node fails, the aborted Docker containers are re-started on the remaining nodes. If the primary MySQL fails, one of the replicas MySQL servers is promoted to the new primary MySQL server, and a new replica Server is started. If one of the replicas MySQL servers fails, a new replica MySQL server is started, provisioned, and configured.

### Step 1 - Setup Docker

Setup your [Docker Swarm](https://docs.docker.com/engine/swarm/). The following commands have to be executed on all nodes of the cluster. As an alternative, you can use the following [Ansible Playbook](https://github.com/jnidzwetzki/ansible-playbooks/tree/main/docker) to install Docker on the cluster.

```bash
apt-get update
apt-get install -y apt-transport-https ca-certificates curl gnupg2 software-properties-common sudo
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable"
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io
```

### Step 2 - Init the Docker Swarm

On one of the nodes, execute the following commands to bootstrap the Docker Swarm:

```bash
docker swarm init --advertise-addr <Public-IP of this node>
```

The command above will show how you can add further _worker nodes_ to the cluster. Worker nodes only execute docker container and do __not__ be part of the cluster management. The node that has inited the cluster will be the only _manager node_ in the cluster. If this node becomes unavailable, the cluster runs into an unhealthy state. Therefore, you should at least have three _manager nodes_ in your cluster. 

To join a new node as _manager node_, execute the following command on a master node and execute the provided command on the new node:

```bash
docker swarm join-token manager
```
The output of the command above should be executed on the worker nodes to join the cluster as managers.

```bash
docker swarm join --token <Token>
```

After executing these commands, the status of the cluster should look as follows:

```bash
$ docker node ls
ID                            HOSTNAME            STATUS              AVAILABILITY        MANAGER STATUS      ENGINE VERSION
cqshak7jcuh97oqtznbcorkjp *   debian10-vm1        Ready               Active              Leader              19.03.13
deihndvm1vwbym9q9x3fyksev     debian10-vm2        Ready               Active              Reachable           19.03.13
3rqp1te4d66tm56b7a1zzlpr2     debian10-vm3        Ready               Active              Reachable           19.03.13
7l21f6mdy0dytmiy4oh70ttjo     debian10-vm4        Ready               Active              Reachable           19.03.13
```

__Note__: Per default, manager nodes also execute Docker containers. This can lead to the situation that a manager node becomes unreliable if a heavy workload is processed; the node is detected as dead, and the workload becomes re-scheduled even if all nodes of the cluster are available. To avoid such situations, in a real-world setup, manager nodes should only interact as manager nodes and not execute any workload. This can be done by executing `docker node update --availability drain <NODE>` for the manager nodes. 

### Step 3 - Deploy the Services

The Deployment of the services to Docker Swarm is done with a [Compose file](https://github.com/jnidzwetzki/mysql-ha-cloud/tree/main/deployment). This file descibes the services of the Docker Swarm cluster. The file can be downloaded and deployed as follows:

```bash
wget https://raw.githubusercontent.com/jnidzwetzki/mysql-ha-cloud/main/deployment/mysql-docker-swarm.yml
docker stack deploy --compose-file mysql-docker-swarm.yml mysql
```

After the deployment is done, the stack should look as follows:

```
$ docker stack ps mysql
ID                  NAME                IMAGE                                      NODE                DESIRED STATE       CURRENT STATE          ERROR               PORTS
u76l3tdmaari        mysql_minio.1       minio/minio:RELEASE.2020-10-18T21-54-12Z   debian10-vm1        Running             Running 12 hours ago                       
0l9tfos9a1x3        mysql_mysql.1       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm1        Running             Running 12 hours ago                       
yv90rhchf8zo        mysql_consul.1      consul:1.8                                 debian10-vm2        Running             Running 12 hours ago                       
8ih671k5quuy        mysql_mysql.2       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm4        Running             Running 12 hours ago                       
q13orlp3rwf0        mysql_consul.2      consul:1.8                                 debian10-vm3        Running             Running 12 hours ago                       
n120oem9bpge        mysql_mysql.3       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm3        Running             Running 12 hours ago                       
mg2xf7pfz5nr        mysql_consul.3      consul:1.8                                 debian10-vm4        Running             Running 12 hours ago   

$ docker stack services mysql
ID                  NAME                MODE                REPLICAS               IMAGE                                      PORTS
2tf6zdffzv4r        mysql_mysql         replicated          3/3 (max 1 per node)   jnidzwetzki/mysql-ha-cloud:latest          
qsqge2j4vhkc        mysql_minio         replicated          1/1                    minio/minio:RELEASE.2020-10-18T21-54-12Z   *:9000->9000/tcp
yap05yt8wkqs        mysql_consul        replicated          3/3 (max 1 per node)   consul:1.8     
```

After the service is deployed, the state of the docker installation can be checked. On the Docker node, the following command can be excuted in one of the consul containers `a856acfc1635`:


```bash
$ docker exec -t a856acfc1635 consul members
Node          Address         Status  Type    Build  Protocol  DC   Segment
87bed4fff4ce  10.0.6.2:8301   alive   server  1.8.5  2         dc1  <all>
a856acfc1635  10.0.6.4:8301   alive   server  1.8.5  2         dc1  <all>
ad114faf9844  10.0.6.3:8301   alive   server  1.8.5  2         dc1  <all>
0a0085a4bdb8  10.0.6.11:8301  alive   client  1.8.4  2         dc1  <default>
85212e1545ff  10.0.6.10:8301  alive   client  1.8.4  2         dc1  <default>
a5f060f2ef02  10.0.6.9:8301   alive   client  1.8.4  2         dc1  <default>
```

In the output above can be seen that the deployment of the Consul servers was successful. Three servers are deployed, and from the MySQL installations, three agents are started. 
