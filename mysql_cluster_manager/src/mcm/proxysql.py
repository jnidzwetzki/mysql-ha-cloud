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

        # Init proxysql
        proxysql_init = ["/usr/bin/proxysql", "--idle-threads", "-c", "/etc/proxysql.cnf", "--initial"]
        subprocess.run(proxysql_init, check=True)

        # Start the proxysql
        # proxysql = ["/usr/bin/proxysql", "--idle-threads", "-c", "/etc/proxysql.cnf"]
        # subprocess.run(proxysql, check=True)

        return True
