"""This file contains the ProxySQL related actions"""

import os
import logging
import subprocess

from mcm.mysql import Mysql

class Proxysql:
    """
    This class encapsulates all ProxySQL related things
    """

    def __init__(self):
        """
        Init the instance
        """
        self.configured_mysql_hosts = ()


    @staticmethod
    def inital_setup():
        """
        Inital setup of ProxySQL
        """
        logging.info("Performing initial ProxySQL setup")

        # Setup Monitoring User
        replication_user = os.environ.get("MYSQL_REPLICATION_USER")
        replication_password = os.environ.get("MYSQL_REPLICATION_PASSWORD")

        Proxysql.perform_sql_query(f"UPDATE global_variables SET variable_value='{replication_user}' "
                                   "WHERE variable_name='mysql-monitor_username'")
        Proxysql.perform_sql_query(f"UPDATE global_variables SET variable_value='{replication_password}' "
                                   "WHERE variable_name='mysql-monitor_password'")

        # Configure read write hostgroup (writer = 1, reader = 2)
        Proxysql.perform_sql_query("DELETE FROM mysql_replication_hostgroups")
        Proxysql.perform_sql_query("INSERT INTO mysql_replication_hostgroups "
                                   "(writer_hostgroup, reader_hostgroup,comment) VALUES (1, 2, 'cluster1')")

        # Configure read write split
        Proxysql.perform_sql_query("INSERT INTO mysql_query_rules (active, match_digest, "
                                   "destination_hostgroup, apply) VALUES (1, '^SELECT.*', 2, 0)")
        Proxysql.perform_sql_query("INSERT INTO mysql_query_rules (active, match_digest, "
                                   "destination_hostgroup, apply) VALUES (1, '^SELECT.*FOR UPDATE', 1, 1)")

        # Configure Application User
        application_user = os.environ.get("MYSQL_APPLICATION_USER")
        application_password = os.environ.get("MYSQL_APPLICATION_PASSWORD")

        Proxysql.perform_sql_query("DELETE FROM mysql_users")
        Proxysql.perform_sql_query("INSERT INTO mysql_users(username, password, default_hostgroup) "
                                   f"VALUES ('{application_user}', '{application_password}', 1)")

        # Persist and activate config
        Proxysql.persist_and_activate_config()

    @staticmethod
    def persist_and_activate_config():
        """
        Persist and activate the ProxySQL configuration
        """
        Proxysql.perform_sql_query("LOAD MYSQL VARIABLES TO RUNTIME")
        Proxysql.perform_sql_query("LOAD MYSQL SERVERS TO RUNTIME")
        Proxysql.perform_sql_query("LOAD MYSQL USERS TO RUNTIME")
        Proxysql.perform_sql_query("LOAD MYSQL QUERY RULES TO RUNTIME")

        Proxysql.perform_sql_query("SAVE MYSQL VARIABLES TO DISK")
        Proxysql.perform_sql_query("SAVE MYSQL SERVERS TO DISK")
        Proxysql.perform_sql_query("SAVE MYSQL USERS TO DISK")
        Proxysql.perform_sql_query("SAVE MYSQL QUERY RULES TO DISK")

    @staticmethod
    def set_mysql_server(mysql_servers):
        """
        Set the backend MySQL server
        """
        logging.info("Removing all old backend MySQL Server")
        Proxysql.perform_sql_query("DELETE FROM mysql_servers")

        for mysql_server in mysql_servers:
            logging.info("Adding %s as backend MySQL Server", mysql_server)
            Proxysql.perform_sql_query("INSERT INTO mysql_servers(hostgroup_id, hostname, port) "
                                       f"VALUES (1, '{mysql_server}', 3306)")

        Proxysql.perform_sql_query("LOAD MYSQL SERVERS TO RUNTIME")
        Proxysql.perform_sql_query("SAVE MYSQL SERVERS TO DISK")

    def update_mysql_server_if_needed(self, current_mysql_servers):
        """
        Update the MySQL-Servers if needed (changed)
        """
        current_mysql_servers.sort()

        if self.configured_mysql_hosts != current_mysql_servers:
            logging.info("MySQL backend has changed (old=%s, new=%s), reconfiguring",
                         self.configured_mysql_hosts, current_mysql_servers)
            Proxysql.set_mysql_server(current_mysql_servers)
            self.configured_mysql_hosts = current_mysql_servers
            return True

        return False

    @staticmethod
    def perform_sql_query(sql):
        """
        Perform a SQL query
        """
        Mysql.execute_statement_or_exit(sql=sql, username="admin", password="admin", database="", port=6032)

    @staticmethod
    def start_proxysql():
        """
        Start the ProxySQL
        """

        # Init proxysql
        proxysql_init = ["/usr/bin/proxysql", "--idle-threads", "-c", "/etc/proxysql.cnf", "--initial"]
        subprocess.run(proxysql_init, check=True)

        # Start the proxysql
        # proxysql = ["/usr/bin/proxysql", "--idle-threads", "-c", "/etc/proxysql.cnf"]
        # subprocess.run(proxysql, check=True)

        return True
