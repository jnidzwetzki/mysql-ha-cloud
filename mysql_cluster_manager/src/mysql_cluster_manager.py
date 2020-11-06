#!/usr/bin/env python3

import os
import sys
import time
import logging
import argparse
import subprocess

import mysql.connector

parser = argparse.ArgumentParser(description='MySQL cluster manager.')

parser.add_argument('operation', metavar='operation', help='Operation to be executed')

def start_consul_agent():
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

def setup_minio():
    logging.info("Setup MinIO agent")

    minio_url = os.environ.get("MINIO_URL")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")

    # Register server
    mc_args = ["mc", "alias", "set", "backup", minio_url, minio_access_key, minio_secret_key]
    subprocess.run(mc_args, check=True)

    # Create bucket
    mc_create_bucket = ["mc", "mb", "backup/mysqlbackup", "-p"]
    subprocess.run(mc_create_bucket, check=True)


def init_mysql_database():
    logging.info("Init MySQL database directory")
    if os.path.isfile("/var/lib/mysql/ib_logfile0"):
        logging.warning("MySQL is already initialized, skipping")
        return

    mysql_init = ["/usr/bin/mysqld", "--initialize-insecure", "--user=mysql"]
    subprocess.run(mysql_init, check=True)


def setup_consul_connection():
    logging.info("Register Consul connection")

def run_mysqld():
    logging.info("Starting MySQL")
    mysql_server = ["/usr/bin/mysqld_safe", "--user=mysql"]
    subprocess.run(mysql_server, check=True)
    wait_for_mysql_connection()

def wait_for_mysql_connection(timeout=30, username='root',
                              password='None', database='mysql'):

    elapsed_time = 0

    while elapsed_time < timeout:
        try:
            cnx = mysql.connector.connect(user=username, password=password,
                                          database=database)
            cnx.close()
            return True
        except mysql.connector.Error:
            elapsed_time = elapsed_time + 1

    return False

def backup_mysql():
    logging.info("Backing up MySQL")
    # mkdir /cluster/mysql
    # xtrabackup --backup --target-dir=/cluster/mysql
    # tar zcvf mysql.tgz mysql
    # mc cp mysql.tgz backup:/

def join_or_bootstrap():
    setup_minio()
    start_consul_agent()
    init_mysql_database()
    setup_consul_connection()
    run_mysqld()

    while True:
        time.sleep(1)

args = parser.parse_args()

if args.operation == 'join_or_bootstrap':
    join_or_bootstrap()

else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
