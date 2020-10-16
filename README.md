# MySQL highly-available cloud container orchestrator
<a href="https://travis-ci.org/jnidzwetzki/mysql-ha-cloud">
  <img alt="Build Status" src="https://travis-ci.org/jnidzwetzki/mysql-ha-cloud.svg?branch=main">
</a>
<a href="http://makeapullrequest.com">
 <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" />
</a>

<a href="https://gitter.im/mysql-ha-cloud/Lobby?utm_source=share-link&utm_medium=link&utm_campaign=share-link">
  <img alt="Join the chat at https://gitter.im/mysql-ha-cloud/Lobby" src="https://badges.gitter.im/Join%20Chat.svg">
</a>
<br>
This project provides containers and blueprints for robust, scalable, and highly-available MySQL installations. 

Project state: Alpha version in development

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

## What is the USP of this project?

This project will provide robust, tested, and easily to deploy containers for self-hosted MySQL cloud installations. The goal is that everybody can deploy highly-available and scalable MySQL installations and eliminate the DBMS as a single point of failure in his architecture.
