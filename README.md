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

## What is the problem?

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
* Three instances (replicated) of the minio object storage to store MySQL backups. These backups are used to bootstrap new MySQL replicas automatically. 
* One primary MySQL server (read/write) and two read-only MySQL replicas. 

All deployed services are running three replicas. Therefore, one Docker node can fail and the services can still be executed.

When one Docker node fails, the aborted Docker containers are re-started on the remaining nodes. If the primary MySQL fails, one of the replicas MySQL servers is promoted to the new primary MySQL server, and a new replica Server is started. If one of the replicas MySQL servers fails, a new replica MySQL server is started, provisioned, and configured.

### Step 1 - Setup Docker

Setup your [Docker Swarm](https://docs.docker.com/engine/swarm/). The following commands have to be executed on all nodes of the cluster. 

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


