"""This file is part of the MySQL cluster manager"""

import os
import time
import json
import logging
import subprocess
import netifaces

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

    # Instances ID key
    instances_path = kv_prefix + "instances/"

    # Instances session key
    instances_session_key = kv_prefix + "instances"

    def __init__(self):
        """
        Init the Consul client
        """
        if Consul.__instance is not None:
            raise Exception("This class is a singleton!")

        Consul.__instance = self
        logging.info("Register Consul connection")
        self.client = pyconsul.Consul(host="localhost")
        self.active_sessions = []

    @staticmethod
    def get_instance():
        """ Static access method. """
        if Consul.__instance is None:
            Consul()
        return Consul.__instance

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

    def register_node(self, mysql_version=None, server_id=None):
        """
        Register the node in Consul
        """
        logging.debug("Register MySQL instance in Consul")

        interface = os.getenv('MCM_BIND_INTERFACE', "eth0")
        ip_address = netifaces.ifaddresses(interface)[netifaces.AF_INET][0]["addr"]

        json_string = json.dumps({
            'ip_address': ip_address,
            'server_id': server_id,
            'mysql_version': mysql_version
        })

        session = self.create_session(name=Consul.instances_session_key,
                                      behavior='delete', ttl=15, lock_delay=0)

        path = f"{Consul.instances_path}{ip_address}"
        logging.debug("Consul: Path %s, value %s (session %s)",
                      path, json_string, session)
        put_result = self.client.kv.put(path, json_string, acquire=session)

        if not put_result:
            logging.error("Unable to create %s", path)
            return False

        return True

    def refresh_sessions(self):
        """
        Refresh the active sessions
        """
        logging.debug("Keeping Consul sessions alive")

        for session in self.active_sessions:
            logging.debug("Refreshing session %s", session)
            self.client.session.renew(session)

    def create_session(self, name, behavior='release', ttl=None, lock_delay=15):
        """
        Create a new session.

        Keep in mind that the real invalidation is around 2*ttl
        see https://github.com/hashicorp/consul/issues/1172
        """

        session_id = self.client.session.create(name=name,
                                                behavior=behavior,
                                                ttl=ttl,
                                                lock_delay=lock_delay)

        # Keep session for auto refresh
        self.active_sessions.append(session_id)

        logging.debug("Created new session on node %s named %s", name, session_id)

        return session_id

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
