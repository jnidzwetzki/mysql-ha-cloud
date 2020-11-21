"""This file contains the actions of the cluster manager"""

import sys
import time
import logging

from datetime import timedelta, datetime

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.mysql import Mysql
from mcm.utils import Utils

class Actions:
    """The actions of the application"""

    @staticmethod
    def join_or_bootstrap():
        """
        Join the existing cluster or bootstrap a new cluster
        """

        Minio.setup_connection()
        consul_process = Consul.agent_start()

        # Check if we have an existing backup to restore
        # Use this backup if exists, or init a new MySQL database
        backup_exists = Minio.does_backup_exists()

        if not backup_exists:
            Mysql.init_database_if_needed()
        else:
            result = Mysql.restore_data()

            if not result:
                logging.error("Unable to restore MySQL backup")
                sys.exit(1)

        mysql_process = Mysql.server_start()

        # Get data from MySQL
        mysql_version = Mysql.execute_query_as_root("SELECT version()")[0]['version()']
        server_id = Mysql.execute_query_as_root("SELECT @@GLOBAL.server_id")[0]['@@GLOBAL.server_id']

        Consul.get_instance().register_node(mysql_version=mysql_version,
                                            server_id=server_id)

        last_backup_check = None
        last_session_refresh = None
        last_replication_leader_check = None

        # Main Loop, heavy operations needs to be dispatched
        # to an extra thread. The loop needs to refresh the
        # Consul sessions every few seconds.
        while True:
            consul_process.poll()
            mysql_process.poll()

            # Try to replace a failed replication leader
            if Utils.is_refresh_needed(last_replication_leader_check, timedelta(seconds=5)):
                last_replication_leader_check = datetime.now()
                if not Consul.get_instance().is_replication_leader():
                    Consul.get_instance().try_to_become_replication_leader()

            # Keep Consul sessions alive
            if Utils.is_refresh_needed(last_session_refresh, timedelta(seconds=5)):
                Consul.get_instance().refresh_sessions()
                last_session_refresh = datetime.now()

            # Create MySQL Backups (using extra thread for backup)
            if Utils.is_refresh_needed(last_backup_check, timedelta(minutes=5)):
                Mysql.create_backup_if_needed()
                last_backup_check = datetime.now()

            time.sleep(1)
