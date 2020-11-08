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

def minio_setup():
    """
    Setup the MinIO agent.
    """

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
    """
    Init a MySQL and configure permissions.
    """

    logging.info("Init MySQL database directory")

    if os.path.isfile("/var/lib/mysql/ib_logfile0"):
        logging.info("MySQL is already initialized, skipping")
        return False

    mysql_init = ["/usr/sbin/mysqld", "--initialize-insecure", "--user=mysql"]

    subprocess.run(mysql_init, check=True)

    # Start server the first time
    mysql_process = mysql_start(use_root_password=False)

    # Create backup user
    logging.debug("Create MySQL user for backups")
    backup_user = os.environ.get("MYSQL_BACKUP_USER")
    backup_password = os.environ.get("MYSQL_BACKUP_PASSWORD")
    execute_mysql_statement(f"CREATE USER '{backup_user}'@'localhost' "
                            f"IDENTIFIED BY '{backup_password}'")
    execute_mysql_statement("GRANT BACKUP_ADMIN, PROCESS, RELOAD, LOCK TABLES, "
                            f"REPLICATION CLIENT ON *.* TO '{backup_user}'@'localhost'")
    execute_mysql_statement("GRANT SELECT ON performance_schema.log_status TO "
                            f"'{backup_user}'@'localhost'")

    # Create replication user
    logging.debug("Create replication user")
    replication_user = os.environ.get("MYSQL_REPLICATION_USER")
    replication_password = os.environ.get("MYSQL_REPLICATION_PASSWORD")
    execute_mysql_statement(f"CREATE USER '{replication_user}'@'%' "
                            f"IDENTIFIED BY '{replication_password}'")
    execute_mysql_statement(f"GRANT REPLICATION SLAVE ON *.* TO '{replication_user}'@'%'")

    # Change permissions for the root user
    logging.debug("Set permissions for the root user")
    root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
    execute_mysql_statement(f"CREATE USER 'root'@'%' IDENTIFIED BY '{root_password}'")
    execute_mysql_statement("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION")
    execute_mysql_statement(f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_password}'")

    # Shutdown MySQL server
    logging.debug("Inital MySQL setup done, shutdown server..")
    execute_mysql_statement(sql="SHUTDOWN", username="root", password=root_password)
    mysql_process.wait()

    return True

def setup_consul_connection():
    """
    Init consul connection.
    """
    logging.info("Register Consul connection")

def mysql_start(use_root_password=True):
    """
    Start the MySQL and wait for ready to serve connections.
    """

    logging.info("Starting MySQL")
    mysql_server = ["/usr/bin/mysqld_safe", "--user=mysql"]
    mysql_process = subprocess.Popen(mysql_server)

    # Use root password for the connection or not
    root_password = None
    if use_root_password:
        root_password = os.environ.get("MYSQL_ROOT_PASSWORD")

    mysql_wait_for_connection(password=root_password)

    return mysql_process

def mysql_wait_for_connection(timeout=30, username='root',
                              password=None, database='mysql'):

    """
    Test connection via unix-socket. During first init
    MySQL start without network access.
    """
    elapsed_time = 0
    last_error = None

    while elapsed_time < timeout:
        try:
            cnx = mysql.connector.connect(user=username, password=password,
                                          database=database,
                                          unix_socket='/var/run/mysqld/mysqld.sock')
            cnx.close()
            logging.debug("MySQL connection successfully")
            return True
        except mysql.connector.Error as err:
            time.sleep(1)
            elapsed_time = elapsed_time + 1
            last_error = err

    logging.error("Unable to connect to MySQL (timeout=%i). %s", elapsed_time, last_error)
    sys.exit(1)

    return False

def execute_mysql_statement(sql=None, username='root',
                            password=None, database='mysql'):

    """
    Execute the given SQL statement.
    """
    try:
        cnx = mysql.connector.connect(user=username, password=password,
                                      database=database, unix_socket='/var/run/mysqld/mysqld.sock')
        cursor = cnx.cursor()

        cursor.execute(sql)

        cnx.close()
        return True
    except mysql.connector.Error as err:
        logging.error("Failed to execute SQL: %s", err)
        sys.exit(1)

def mysql_backup():
    """
    Backup the local MySQL Server and upload
    the backup into a S3 bucket.
    """

    # Call Setup to ensure bucket and policies do exist
    minio_setup()

    current_time = time.time()
    backup_dir = f"/tmp/mysql_backup_{current_time}"

    logging.info("Backing up MySQL into dir %s", backup_dir)
    if os.path.exists(backup_dir):
        logging.error("Backup path %s already exists, skipping backup run", backup_dir)

    # Crate backup dir
    os.makedirs(backup_dir)

    # Create mysql backup
    backup_user = os.environ.get("MYSQL_BACKUP_USER")
    backup_password = os.environ.get("MYSQL_BACKUP_PASSWORD")
    xtrabackup = ["/usr/bin/xtrabackup", f"--user={backup_user}",
                  f"--password={backup_password}", "--backup",
                  f"--target-dir={backup_dir}"]

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
    """
    Join the existing cluster or bootstrap a new cluster
    """

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
