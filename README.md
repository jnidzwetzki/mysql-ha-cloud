# MySQL highly-available cloud container

This project provides containers and blueprints for a highly-available MySQL installation. 

## What is the problem?

In today's software development, applications are developed as stateless cloud-native applications and provisioned as stateless containers. These containers can be easily moved between hosts, automatically restarted on failures, or replicated to handle increasing workloads. On the other hand, the data is stored in relational database systems (RDBMS), which are often running on bare-metal hardware. Relational databases are stateful applications that are hard to scale. High availability (HA) is rarely implemented. The HA architecture is often based on concepts that do not fit into a cloud architecture (e.g., fail-over solutions using IP switching). In addition, most tutorials on the internet contain weaknesses (e.g., they are still recommending to use mysqldump to dump a production database. This blocks the whole application during the backup process). 

## Are NoSQL databases a solution?

NoSQL databases are mostly cloud-native applications; however, they leak of the support of a full flagged relational database. Features such as transactions, complex data models, or consistency are omitted to make these systems horizontal scalable and fault-tolerant. However, simple tasks that can easily be implemented by using a relational database (e.g., an increasing counter, secondary indexes, isolation of uncommitted data, or joins) can be hard to implement. Therefore, relational databases are still used by moderns applications. 
