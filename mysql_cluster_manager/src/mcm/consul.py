"""This file is part of the MySQL cluster manager"""

import os
import time
import json
import logging
import subprocess

import consul as pyconsul

class Consul:

    """
    This class encapsulates all Consul related things
    """

    # The signeton instance
    __instance = None

    # Retry counter for operations
    retry_counter = 100

    # KV prefix
    kv_prefix = "mcm/"

    # Server ID key
    kv_server_id = kv_prefix + "server_id"

    @staticmethod
    def get_instance():
        """ Static access method. """
        if Consul.__instance is None:
            Consul()
        return Consul.__instance

    def __init__(self):
        """
        Init the Consul client
        """
        if Consul.__instance is not None:
            raise Exception("This class is a singleton!")

        Consul.__instance = self
        logging.info("Register Consul connection")
        self.client = pyconsul.Consul(host="localhost")

    def get_mysql_server_id(self):
        """
        Get the MySQL server id from consul

        Try to get existing value and update to +1
          * If Update fails, retry
          * If Key not exists, try to create
        """
        for _ in range(Consul.retry_counter):
            result = self.client.kv.get(Consul.kv_server_id)

            # Create new key
            if result[1] is None:
                logging.debug("Old serverkey %s not found, preparing new one",
                              Consul.kv_server_id)

                json_string = json.dumps({'last_used_id': 1})

                # Try to create
                put_result = self.client.kv.put(Consul.kv_server_id, json_string, cas=0)
                if put_result is True:
                    logging.debug("Created new key, started new server counter")
                    return 1

                logging.debug("New key could not be created, retrying")
                continue

            # Updating existing key
            logging.debug("Updating existing key %s", result)
            json_string = result[1]['Value']
            version = result[1]['ModifyIndex']
            server_data = json.loads(json_string)

            if not "last_used_id" in server_data:
                logging.error("Invalid JSON returned (missing last_used_id) %s",
                              json_string)

            server_data['last_used_id'] = server_data['last_used_id'] + 1
            json_string = json.dumps(server_data)
            put_result = self.client.kv.put(Consul.kv_server_id, json_string, cas=version)

            if put_result is True:
                logging.debug("Successfully updated consul value %s, new server_id is %i",
                              put_result, server_data['last_used_id'])
                return server_data['last_used_id']

            logging.debug("Unable to update consul value, retrying %s", put_result)
            time.sleep(10)

        raise Exception("Unable to determine server id")

    # pylint: disable=no-self-use
    def is_mysql_master(self):
        """
        Test if this is the MySQL replication master or not
        """

        return True

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
