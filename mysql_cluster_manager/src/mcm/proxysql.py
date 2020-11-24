"""This file contains the ProxySQL related actions"""

import subprocess

class Proxysql:
    """
    This class encapsulates all ProxySQL related things
    """

    @staticmethod
    def start_proxysql():
        """
        Start the ProxySQL
        """

        # Start the proxysql
        proxysql = ["/etc/init.d/proxysql", "start"]
        subprocess.run(proxysql, check=True)

        return True

    @staticmethod
    def stop_proxysql():
        """
        Stop the ProxySQL
        """

        # Stop the proxysql
        proxysql = ["/etc/init.d/proxysql", "stop"]
        subprocess.run(proxysql, check=True)

        return True
