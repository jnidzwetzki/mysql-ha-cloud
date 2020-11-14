"""This file contains the actions of the cluster manager"""

import sys
import time
import logging

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.mysql import Mysql

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
        last_backup = Minio.get_latest_backup_file()

        if last_backup is None:
            result = Mysql.init_database()

            if not result:
                logging.error("Unable to init MySQL database")
                sys.exit(1)
        else:
            result = Mysql.restore_data()

            if not result:
                logging.error("Unable to restore MySQL backup")
                sys.exit(1)

        Consul.setup_connection()
        mysql_process = Mysql.server_start()

        while True:
            consul_process.poll()
            mysql_process.poll()
            time.sleep(1)
