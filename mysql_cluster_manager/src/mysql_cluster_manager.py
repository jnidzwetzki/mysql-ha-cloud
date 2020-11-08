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
log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
parser.add_argument('--log-level', default='INFO', choices=log_levels)

def consul_agent_start():
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

def minio_setup():
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


def mysql_init_database():
    logging.info("Init MySQL database directory")

    if os.path.isfile("/var/lib/mysql/ib_logfile0"):
        logging.info("MySQL is already initialized, skipping")
        return False

    mysql_init = ["/usr/sbin/mysqld", "--initialize-insecure", "--user=mysql"]

    subprocess.run(mysql_init, check=True)

    mysql_process = mysql_start()

    # Create Backup User
    logging.debug("Create MySQL user..")
    execute_mysql_statement("CREATE USER 'bkpuser'@'localhost' IDENTIFIED BY 's3cret'")
    execute_mysql_statement("GRANT RELOAD, LOCK TABLES, PROCESS, "
                            "REPLICATION CLIENT ON *.* TO'bkpuser'@'localhost'")

    # Shutdown MySQL server
    logging.debug("Inital MySQL setup done, shutdown server..")
    execute_mysql_statement(sql="SHUTDOWN")
    mysql_process.wait()

    return True


def setup_consul_connection():
    logging.info("Register Consul connection")

def mysql_start():
    logging.info("Starting MySQL")
    mysql_server = ["/usr/bin/mysqld_safe", "--user=mysql"]
    mysql_process = subprocess.Popen(mysql_server)

    mysql_wait_for_connection()

    return mysql_process

def mysql_wait_for_connection(timeout=30, username='root',
                              password=None, database='mysql'):

    elapsed_time = 0

    while elapsed_time < timeout:
        try:
            cnx = mysql.connector.connect(user=username, password=password,
                                          database=database)
            cnx.close()
            return True
        except mysql.connector.Error:
            elapsed_time = elapsed_time + 1

    logging.error("Unable to connect to MySQL")
    return False

def execute_mysql_statement(sql=None, username='root',
                            password=None, database='mysql'):

    try:
        cnx = mysql.connector.connect(user=username, password=password,
                                      database=database)
        cursor = cnx.cursor()

        cursor.execute(sql)

        cnx.close()
        return True
    except mysql.connector.Error as err:
        logging.error("Failed to execute SQL: %s", err)
        sys.exit(1)

def mysql_backup():
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
    minio_setup()
    consul_process = consul_agent_start()
    mysql_init_database()
    setup_consul_connection()
    mysql_process = mysql_start()

    while True:
        consul_process.poll()
        mysql_process.poll()
        time.sleep(1)

args = parser.parse_args()

logging.basicConfig(level=args.log_level,
                    format='%(levelname)s %(name)s %(message)s')

if args.operation == 'join_or_bootstrap':
    join_or_bootstrap()
elif args.operation == 'minio_setup':
    minio_setup()
elif args.operation == 'mysql_backup':
    mysql_backup()
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
