"""This file contains the actions of the cluster manager"""

import sys
import time
import logging

from datetime import timedelta, datetime

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
        backup_exists = Minio.does_backup_exists()

        if not backup_exists:
            Mysql.init_database_if_needed()
        else:
            result = Mysql.restore_data()

            if not result:
                logging.error("Unable to restore MySQL backup")
                sys.exit(1)

        mysql_process = Mysql.server_start()

        last_backup_check = None

        while True:
            consul_process.poll()
            mysql_process.poll()

            if last_backup_check is None:
                Mysql.create_backup_if_needed()
                last_backup_check = datetime.now()

            elif datetime.now() - last_backup_check > timedelta(minutes=5):
                Mysql.create_backup_if_needed()
                last_backup_check = datetime.now()

            time.sleep(1)
