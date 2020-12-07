# Example - Using Docker Swarm

In this example, a cluster consisting of five nodes running Debian 10 is used. The following services are deployed on the cluster:

* Five Consul instances, they are used for election of the primary MySQL server, for service discovery, and for providing additional information about the state of the cluster.
* One of the MinIO object storage to store MySQL backups. These backups are used to bootstrap new MySQL replicas automatically. MinIO needs at least to provide four nodes / volumes to provide highly available. In addition, deploying such a setup without labeling the Docker nodes and creating stateful volumes is hard. The data on the S3 Bucket are re-written periodically. Therefore, we don't deploy a highly available and replicated version of MinIO in this example.
* One primary MySQL server (read/write) and two read-only MySQL replicas. 
* An instance of [ProxySQL](https://github.com/sysown/proxysql) is available on every MySQL-Server. ProxySQL is used to access the MySQL installations. Write requests (e.g., `INSERT` or `UPDATE`) are automatically send to the replication leader, and read requests (e.g., `SELECT`) are sent to the replication follower.

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
uttuejl2q48hwizz3bya5engw     debian10-vm5        Ready               Active              Reachable           19.03.13
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
ID                  NAME                IMAGE                                      NODE                DESIRED STATE       CURRENT STATE                  ERROR               PORTS
zywtlmvswfz1        mysql_minio.1       minio/minio:RELEASE.2020-10-18T21-54-12Z   debian10-vm4        Running             Running 53 seconds ago                             
v8hks8xa6vub        mysql_mysql.1       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm2        Running             Preparing about a minute ago                       
bhsvp0muev51        mysql_consul.1      consul:1.8                                 debian10-vm1        Running             Running about a minute ago                         *:8500->8500/tcp
4no74auuqpv0        mysql_mysql.2       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm3        Running             Preparing about a minute ago                       
t1dan93zja0e        mysql_consul.2      consul:1.8                                 debian10-vm2        Running             Running about a minute ago                         *:8500->8500/tcp
0b3pyj32v5db        mysql_mysql.3       jnidzwetzki/mysql-ha-cloud:latest          debian10-vm1        Running             Preparing about a minute ago                       
gptp9fpmkw4r        mysql_consul.3      consul:1.8                                 debian10-vm4        Running             Running about a minute ago                         *:8500->8500/tcp
i2egrq1cbieu        mysql_consul.4      consul:1.8                                 debian10-vm5        Running             Running 32 seconds ago                             *:8500->8500/tcp
vvsf1wwb1zr2        mysql_consul.5      consul:1.8                                 debian10-vm3        Running             Running about a minute ago                         *:8500->8500/tcp

$ docker stack services mysql
ID                  NAME                MODE                REPLICAS               IMAGE                                      PORTS
0v8qhwaaawx5        mysql_minio         replicated          1/1                    minio/minio:RELEASE.2020-10-18T21-54-12Z   *:9000->9000/tcp
pro64635i2j4        mysql_mysql         replicated          3/3 (max 1 per node)   jnidzwetzki/mysql-ha-cloud:latest          
ya9luugwcri4        mysql_consul        replicated          5/5 (max 1 per node)   consul:1.8       
```

After the service is deployed, the state of the docker installation can be checked. On the Docker node, the following command can be excuted in one of the consul containers `a856acfc1635`:


```bash
$ docker exec -t a856acfc1635 consul members
Node          Address         Status  Type    Build  Protocol  DC   Segment
234d94d9063f  10.0.3.3:8301   alive   server  1.8.5  2         dc1  <all>
753784b1624a  10.0.3.5:8301   alive   server  1.8.5  2         dc1  <all>
cba13bbba731  10.0.3.2:8301   alive   server  1.8.5  2         dc1  <all>
f00780b002e8  10.0.3.6:8301   alive   server  1.8.5  2         dc1  <all>
f418f8ae1023  10.0.3.4:8301   alive   server  1.8.5  2         dc1  <all>
0d744a098502  10.0.3.40:8301  alive   client  1.8.4  2         dc1  <default>
72e398e0f1bc  10.0.3.41:8301  alive   client  1.8.4  2         dc1  <default>
9e96a9596e76  10.0.3.42:8301  alive   client  1.8.4  2         dc1  <default>
```

In the output above can be seen that the deployment of the Consul servers was successful. Three servers are deployed, and from the MySQL installations, three agents are started. 

### Step 4 - Check Deployment

After the deployment is done, you can check which MySQL nodes are avaialable and which node is the replication leader:

```bash
$ docker exec -t a856acfc1635 consul kv get -recurse mcm/instances
mcm/instances/10.0.3.40:{"ip_address": "10.0.3.40", "server_id": 44, "mysql_version": "8.0.21"}
mcm/instances/10.0.3.41:{"ip_address": "10.0.3.41", "server_id": 45, "mysql_version": "8.0.21"}
mcm/instances/10.0.3.42:{"ip_address": "10.0.3.42", "server_id": 46, "mysql_version": "8.0.21"}

$ docker exec -t a856acfc1635 consul kv get mcm/replication_leader
{"ip_address": "10.0.3.41"}
```

In addition, you can have a look at the MySQL replication configuration

```bash
$ docker exec -t a856acfc1635 /bin/bash -c 'mysql -u root -p`echo $MYSQL_ROOT_PASSWORD` -e "SHOW SLAVE STATUS"'
mysql: [Warning] Using a password on the command line interface can be insecure.
+----------------------------------+-------------+------------------+-------------+---------------+-----------------+---------------------+-------------------------------+---------------+-----------------------+------------------+-------------------+-----------------+---------------------+--------------------+------------------------+-------------------------+-----------------------------+------------+------------+--------------+---------------------+-----------------+-----------------+----------------+---------------+--------------------+--------------------+--------------------+-----------------+-------------------+----------------+-----------------------+-------------------------------+---------------+---------------+----------------+----------------+-----------------------------+------------------+--------------------------------------+-------------------------+-----------+---------------------+--------------------------------------------------------+--------------------+-------------+-------------------------+--------------------------+----------------+--------------------+--------------------+----------------------------------------------------------------------------------+---------------+----------------------+--------------+--------------------+------------------------+-----------------------+-------------------+
| Slave_IO_State                   | Master_Host | Master_User      | Master_Port | Connect_Retry | Master_Log_File | Read_Master_Log_Pos | Relay_Log_File                | Relay_Log_Pos | Relay_Master_Log_File | Slave_IO_Running | Slave_SQL_Running | Replicate_Do_DB | Replicate_Ignore_DB | Replicate_Do_Table | Replicate_Ignore_Table | Replicate_Wild_Do_Table | Replicate_Wild_Ignore_Table | Last_Errno | Last_Error | Skip_Counter | Exec_Master_Log_Pos | Relay_Log_Space | Until_Condition | Until_Log_File | Until_Log_Pos | Master_SSL_Allowed | Master_SSL_CA_File | Master_SSL_CA_Path | Master_SSL_Cert | Master_SSL_Cipher | Master_SSL_Key | Seconds_Behind_Master | Master_SSL_Verify_Server_Cert | Last_IO_Errno | Last_IO_Error | Last_SQL_Errno | Last_SQL_Error | Replicate_Ignore_Server_Ids | Master_Server_Id | Master_UUID                          | Master_Info_File        | SQL_Delay | SQL_Remaining_Delay | Slave_SQL_Running_State                                | Master_Retry_Count | Master_Bind | Last_IO_Error_Timestamp | Last_SQL_Error_Timestamp | Master_SSL_Crl | Master_SSL_Crlpath | Retrieved_Gtid_Set | Executed_Gtid_Set                                                                | Auto_Position | Replicate_Rewrite_DB | Channel_Name | Master_TLS_Version | Master_public_key_path | Get_master_public_key | Network_Namespace |
+----------------------------------+-------------+------------------+-------------+---------------+-----------------+---------------------+-------------------------------+---------------+-----------------------+------------------+-------------------+-----------------+---------------------+--------------------+------------------------+-------------------------+-----------------------------+------------+------------+--------------+---------------------+-----------------+-----------------+----------------+---------------+--------------------+--------------------+--------------------+-----------------+-------------------+----------------+-----------------------+-------------------------------+---------------+---------------+----------------+----------------+-----------------------------+------------------+--------------------------------------+-------------------------+-----------+---------------------+--------------------------------------------------------+--------------------+-------------+-------------------------+--------------------------+----------------+--------------------+--------------------+----------------------------------------------------------------------------------+---------------+----------------------+--------------+--------------------+------------------------+-----------------------+-------------------+
| Waiting for master to send event | 10.0.3.41   | replication_user |        3306 |            60 | binlog.000024   |                 196 | 82df8cfe97e2-relay-bin.000002 |           365 | binlog.000024         | Yes              | Yes               |                 |                     |                    |                        |                         |                             |          0 |            |            0 |                 196 |             581 | None            |                |             0 | No                 |                    |                    |                 |                   |                |                     0 | No                            |             0 |               |              0 |                |                             |               45 | f2260821-2ced-11eb-89ef-02420a000329 | mysql.slave_master_info |         0 |                NULL | Slave has read all relay log; waiting for more updates |              86400 |             |                         |                          |                |                    |                    | 1256e020-2cfe-11eb-a273-02420a00032a:1, 4aa0562f-28ac-11eb-93fa-02420a000305:1-8 |             1 |                      |              |                    |                        |                     1 |                   |
+----------------------------------+-------------+------------------+-------------+---------------+-----------------+---------------------+-------------------------------+---------------+-----------------------+------------------+-------------------+-----------------+---------------------+--------------------+------------------------+-------------------------+-----------------------------+------------+------------+--------------+---------------------+-----------------+-----------------+----------------+---------------+--------------------+--------------------+--------------------+-----------------+-------------------+----------------+-----------------------+-------------------------------+---------------+---------------+----------------+----------------+-----------------------------+------------------+--------------------------------------+-------------------------+-----------+---------------------+--------------------------------------------------------+--------------------+-------------+-------------------------+--------------------------+----------------+--------------------+--------------------+----------------------------------------------------------------------------------+---------------+----------------------+--------------+--------------------+------------------------+-----------------------+-------------------+
```

Or list the available backups of the database:

```bash
$ docker exec -t a856acfc1635  mc ls backup/mysqlbackup
[2020-11-20 21:50:24 UTC] 1.6MiB mysql_backup_1605909015.0471048.tgz
[2020-11-20 21:50:34 UTC] 1.6MiB mysql_backup_1605909024.6657646.tgz
[2020-11-21 03:51:21 UTC] 1.6MiB mysql_backup_1605930672.1543853.tgz
[2020-11-21 09:52:18 UTC] 1.6MiB mysql_backup_1605952329.1124055.tgz
[2020-11-22 12:46:39 UTC] 1.6MiB mysql_backup_1606049190.0292351.tgz
[2020-11-22 18:50:19 UTC] 1.6MiB mysql_backup_1606071009.6974795.tgz
```

The DNS settings for the service discovery could also be tested:

```bash
$ docker exec -t a856acfc1635 dig @127.0.0.1 -p 8600 _mysql._leader.service.consul SRV

; <<>> DiG 9.11.5-P4-5.1+deb10u2-Debian <<>> @127.0.0.1 -p 8600 _mysql._leader.service.consul SRV
; (1 server found)
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 61130
;; flags: qr aa rd; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 3
;; WARNING: recursion requested but not available

;; OPT PSEUDOSECTION:
; EDNS: version: 0, flags:; udp: 4096
;; QUESTION SECTION:
;_mysql._leader.service.consul.	IN	SRV

;; ANSWER SECTION:
_mysql._leader.service.consul. 0 IN	SRV	1 1 3306 cd1e7b5ae9a4.node.dc1.consul.

;; ADDITIONAL SECTION:
cd1e7b5ae9a4.node.dc1.consul. 0	IN	A	10.0.3.41
cd1e7b5ae9a4.node.dc1.consul. 0	IN	TXT	"consul-network-segment="

;; Query time: 1 msec
;; SERVER: 127.0.0.1#8600(127.0.0.1)
;; WHEN: Tue Nov 24 07:06:10 UTC 2020
;; MSG SIZE  rcvd: 158



$ docker exec -t a856acfc1635 dig @127.0.0.1 -p 8600 _mysql._follower.service.consul SRV

; <<>> DiG 9.11.5-P4-5.1+deb10u2-Debian <<>> @127.0.0.1 -p 8600 _mysql._follower.service.consul SRV
; (1 server found)
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 46995
;; flags: qr aa rd; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 5
;; WARNING: recursion requested but not available

;; OPT PSEUDOSECTION:
; EDNS: version: 0, flags:; udp: 4096
;; QUESTION SECTION:
;_mysql._follower.service.consul. IN	SRV

;; ANSWER SECTION:
_mysql._follower.service.consul. 0 IN	SRV	1 1 3306 f36ddfed8617.node.dc1.consul.
_mysql._follower.service.consul. 0 IN	SRV	1 1 3306 ddcadd280a98.node.dc1.consul.

;; ADDITIONAL SECTION:
f36ddfed8617.node.dc1.consul. 0	IN	A	10.0.3.40
f36ddfed8617.node.dc1.consul. 0	IN	TXT	"consul-network-segment="
ddcadd280a98.node.dc1.consul. 0	IN	A	10.0.3.42
ddcadd280a98.node.dc1.consul. 0	IN	TXT	"consul-network-segment="

;; Query time: 1 msec
;; SERVER: 127.0.0.1#8600(127.0.0.1)
;; WHEN: Tue Nov 24 07:06:20 UTC 2020
;; MSG SIZE  rcvd: 260
```

### Step 5 - Use the highly-available MySQL-Server

On port `3306/tcp` (the default MySQL port) on all Docker nodes, you can now reach the highly-available MySQL-Server. As user use `MYSQL_APPLICATION_USER` and the `MYSQL_APPLICATION_PASSWORD` from the docker-swarm file. 

For example: 

```bash
mysql -u mysql_user -pmysql_secret -h debian10-vm1
```

While you work on the MySQL-Shell you can restart the Docker nodes. Docker Swarm will restart the missing sevices on other nodes and the MySQL orchestrator will reconfigure the replication setup in MySQL. The MySQL-Shell is usable all the time for read- and write requests.
