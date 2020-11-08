#!/usr/bin/env python3

import os
import sys
import time
import logging
import argparse
import subprocess

from shutil import rmtree

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

    bucket_name = "backup/mysqlbackup"

    # Register server
    mc_args = ["mc", "alias", "set", "backup", minio_url, minio_access_key, minio_secret_key]
    subprocess.run(mc_args, check=True)

    # Create bucket
    mc_create_bucket = ["mc", "mb", bucket_name, "-p"]
    subprocess.run(mc_create_bucket, check=True)

    # Set expire policy on bucket
    mc_set_policy_bucket = ["mc", "ilm", "set", "--id=expire_rule", "-expiry-days=7", bucket_name]
    subprocess.run(mc_set_policy_bucket, check=True)

def init_mysql_database():
    logging.info("Init MySQL database directory")
    if os.path.isfile("/var/lib/mysql/ib_logfile0"):
        logging.warning("MySQL is already initialized, skipping")
        return

    mysql_init = ["/usr/sbin/mysqld", "--initialize-insecure", "--user=mysql"]
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
    current_time = time.time()
    backup_dir = f"/tmp/mysql_backup_{current_time}"

    logging.info("Backing up MySQL into dir %s", backup_dir)
    if os.path.exists(backup_dir):
        logging.error("Backup path %s already exists, skipping backup run", backup_dir)

    # Crate backup dir
    os.makedirs(backup_dir)

    # Create mysql backup
    xtrabackup = ["/usr/bin/xtrabackup", "--backup", f"--target-dir={backup_dir}"]
    subprocess.run(xtrabackup, check=True)

    # Compress backup
    backup_file = f"/tmp/mysql_backup_{current_time}.tgz"
    tar = ["/bin/tar", "zcf", backup_file, backup_dir]
    subprocess.run(tar, check=True)

    # Upload Backup to S3 Bucket
    mc_args = ["/usr/local/bin/mc", "cp", backup_file, "backup/mysqlbackup/"]
    subprocess.run(mc_args, check=True)

    # Remove old backup data
    rmtree(backup_dir)
    os.remove(backup_file)

    logging.info("Backup was successfully created")

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
elif args.operation == 'minio_setup':
    setup_minio()
elif args.operation == 'mysql_backup':
    backup_mysql()
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
