"""This file contains the utils of the cluster manager"""

import os

from datetime import datetime

import netifaces

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
