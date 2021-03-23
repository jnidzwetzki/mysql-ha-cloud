"""This file contains the actions of the cluster manager"""

import sys
import time
import logging

from datetime import timedelta, datetime

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.mysql import Mysql
from mcm.proxysql import Proxysql
from mcm.utils import Utils

class Actions:
    """The actions of the application"""

    @staticmethod
    def join_or_bootstrap():
        """
        Join the existing cluster or bootstrap a new cluster
        """

        # Start the local consul agent
        consul_process = Consul.agent_start()

        # Check if we have an existing backup to restore
        # Use this backup if exists, or init a new MySQL database
        Minio.setup_connection()
        backup_exists = Minio.does_backup_exists()

        # Test for unstable environment (other nodes are present and no leader is present)
        # We don't want to become the new leader on the restored backup directly
        #
        # Needs be be checked before Consul.get_instance().register_node() is called
        #
        while Consul.get_instance().get_replication_leader_ip() is None:
            nodes = Consul.get_instance().get_all_registered_nodes()
            if len(nodes) == 0:
                break

            logging.warning("Other nodes (%s) detected but no leader, waiting", nodes)
            time.sleep(5)

        # Try to become session leader (needed to decide if we can create a database)
        replication_leader = Consul.get_instance().try_to_become_replication_leader()

        # Keep session alive until we start the main loop
        Consul.get_instance().start_session_auto_refresh_thread()

        logging.info("Init local node (leader=%s, backup=%s)",
                     replication_leader, backup_exists)

        if replication_leader and not backup_exists:
            Mysql.init_database_if_needed()
        elif replication_leader and backup_exists:
            Mysql.restore_backup_or_exit()
        elif not replication_leader and backup_exists:
            Mysql.restore_backup_or_exit()
        elif not replication_leader and not backup_exists:
            logging.info("We are not the replication leader, waiting for backups")
            backup_exists = Utils.wait_for_backup_exists(Consul.get_instance())

            if not backup_exists:
                logging.error("No backups to restore available, please check master logs, exiting")
                sys.exit(1)

            Mysql.restore_backup_or_exit()

        else:
            logging.error("This case should not happen (leader=%s, backup=%s)",
                          replication_leader, backup_exists)
            sys.exit(1)

        # Start ProxySQL
        Proxysql.start_proxysql()

        # Start MySQL
        mysql_process = Mysql.server_start()

        # Configure ProxySQL
        Proxysql.inital_setup()

        # Get data from MySQL
        mysql_version = Mysql.execute_query_as_root("SELECT version()")[0]['version()']
        server_id = Mysql.execute_query_as_root("SELECT @@GLOBAL.server_id")[0]['@@GLOBAL.server_id']

        Consul.get_instance().register_node(mysql_version=mysql_version,
                                            server_id=server_id)

        # Remove the old replication configuration (e.g., from backup)
        Mysql.delete_replication_config()

        # Register service as leader or follower
        Consul.get_instance().register_service(replication_leader)

        # Session keep alive will be handled by the main event loop
        Consul.get_instance().stop_session_auto_refresh_thread()

        # Run the main event loop
        Actions.join_main_event_loop(consul_process, mysql_process)

    @staticmethod
    def join_main_event_loop(consul_process, mysql_process):
        """
        The main event loop for the join_or_bootstrap action
        """

        last_backup_check = None
        last_session_refresh = None
        last_replication_leader_check = None
        able_to_become_leader = False

        proxysql = Proxysql()

        # Main Loop, heavy operations needs to be dispatched
        # to an extra thread. The loop needs to refresh the
        # Consul sessions every few seconds.
        while True:
            consul_process.poll()
            mysql_process.poll()

            # Try to replace a failed replication leader
            if Utils.is_refresh_needed(last_replication_leader_check, timedelta(seconds=5)):
                last_replication_leader_check = datetime.now()

                # Update ProxySQL nodes
                mysql_nodes = Consul.get_instance().get_all_registered_nodes()
                proxysql.update_mysql_server_if_needed(mysql_nodes)

                # Are the replication data completely processed
                # (i.e., the data from the leader is stored locally and we
                # can become the new leader?)
                if not able_to_become_leader:
                    if Mysql.is_repliation_data_processed():
                        logging.info("All replication data are read, node can become replication leader")
                        able_to_become_leader = True

                replication_leader = Consul.get_instance().is_replication_leader()

                # Try to become new leader
                if not replication_leader and able_to_become_leader:
                    promotion = Consul.get_instance().try_to_become_replication_leader()

                    # Are we the new leader?
                    if promotion:
                        Mysql.delete_replication_config()
                        Consul.get_instance().register_service(True)
                        replication_leader = True

                # Check for correct replication leader
                if not replication_leader:
                    real_leader = Consul.get_instance().get_replication_leader_ip()
                    configured_leader = Mysql.get_replication_leader_ip()

                    if real_leader != configured_leader:
                        logging.info("Replication leader change (old=%s, new=%s)", configured_leader, real_leader)
                        Mysql.change_to_replication_client(real_leader)

            # Keep Consul sessions alive
            if Utils.is_refresh_needed(last_session_refresh, timedelta(seconds=5)):
                Consul.get_instance().refresh_sessions()
                last_session_refresh = datetime.now()

            # Create MySQL Backups (using extra thread for backup)
            if Utils.is_refresh_needed(last_backup_check, timedelta(minutes=5)):
                Consul.get_instance().start_session_auto_refresh_thread()
                Mysql.create_backup_if_needed()
                last_backup_check = datetime.now()
                Consul.get_instance().stop_session_auto_refresh_thread()

            time.sleep(1)
