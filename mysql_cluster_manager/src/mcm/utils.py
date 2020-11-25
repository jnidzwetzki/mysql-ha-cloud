"""This file contains the utils of the cluster manager"""

import os
import time

from datetime import datetime

import netifaces

from mcm.minio import Minio


class Utils:
    """
    Utilities for the project
    """

    @staticmethod
    def get_local_ip_address():
        """
        Get the local IP Address
        """

        interface = os.getenv('MCM_BIND_INTERFACE', "eth0")
        return netifaces.ifaddresses(interface)[netifaces.AF_INET][0]["addr"]

    @staticmethod
    def is_refresh_needed(last_execution, max_timedelta):
        """
        Is a new execution needed, based on the time delta
        """
        if last_execution is None:
            return True

        return datetime.now() - last_execution > max_timedelta

    @staticmethod
    def wait_for_backup_exists(consul):
        """
        Wait for a backup to be occour
        """

        Minio.setup_connection()

        retry_counter = 100

        for _ in range(retry_counter):
            backup_exists = Minio.does_backup_exists()

            if backup_exists:
                return True

        # Keep consul sessions alive
        consul.refresh_sessions()
        time.sleep(5000)

        return False
