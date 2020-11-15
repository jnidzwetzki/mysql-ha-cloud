"""This file is part of the MySQL cluster manager"""

import os
import logging
import subprocess

import consul as pyconsul

class Consul:

    """
    This class encapsulates all Consul related things
    """

    def __init__(self):
        """
        Init the Consul client
        """
        self.client = None

    def setup_connection(self):
        """
        Init consul connection.
        """
        logging.info("Register Consul connection")
        self.client = pyconsul.Consul(host="localhost")

    @staticmethod
    def agent_start():
        """
        Start the local Consul agent.
        """

        logging.info("Starting Consul Agent")
        consul_args = ["consul"]
        consul_args.append("agent")
        consul_args.append("--data-dir")
        consul_args.append("/tmp/consul")

        consul_interface = os.environ.get("CONSUL_BIND_INTERFACE")

        if consul_interface is not None:
            consul_args.append("--bind")
            consul_args.append(f'{{{{ GetInterfaceIP "{consul_interface}" }}}}')

        consul_seed = os.environ.get("CONSUL_BOOTSTRAP_SERVER")

        if consul_seed is not None:
            consul_args.append("--join")
            consul_args.append(consul_seed)

        # Run process in background
        consul_process = subprocess.Popen(consul_args)

        return consul_process
