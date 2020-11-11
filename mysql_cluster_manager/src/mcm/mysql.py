"""This file is part of the MySQL cluster manager"""

import os
import sys
import time
import logging
import subprocess

from shutil import rmtree

import mysql.connector

from mcm.minio import Minio

class Mysql:

    """
    This class encapsulates all Mysql related things
    """

    @staticmethod
    def init_database():
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
        mysql_process = Mysql.server_start(use_root_password=False)

        # Create backup user
        logging.debug("Creating MySQL user for backups")
        backup_user = os.environ.get("MYSQL_BACKUP_USER")
        backup_password = os.environ.get("MYSQL_BACKUP_PASSWORD")
        Mysql.execute_statement(f"CREATE USER '{backup_user}'@'localhost' "
                                f"IDENTIFIED BY '{backup_password}'")
        Mysql.execute_statement("GRANT BACKUP_ADMIN, PROCESS, RELOAD, LOCK TABLES, "
                                f"REPLICATION CLIENT ON *.* TO '{backup_user}'@'localhost'")
        Mysql.execute_statement("GRANT SELECT ON performance_schema.log_status TO "
                                f"'{backup_user}'@'localhost'")

        # Create replication user
        logging.debug("Creating replication user")
        replication_user = os.environ.get("MYSQL_REPLICATION_USER")
        replication_password = os.environ.get("MYSQL_REPLICATION_PASSWORD")
        Mysql.execute_statement(f"CREATE USER '{replication_user}'@'%' "
                                f"IDENTIFIED BY '{replication_password}'")
        Mysql.execute_statement(f"GRANT REPLICATION SLAVE ON *.* TO '{replication_user}'@'%'")

        # Change permissions for the root user
        logging.debug("Set permissions for the root user")
        root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
        Mysql.execute_statement(f"CREATE USER 'root'@'%' IDENTIFIED BY '{root_password}'")
        Mysql.execute_statement("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' "
                                "WITH GRANT OPTION")
        Mysql.execute_statement("ALTER USER 'root'@'localhost' "
                                f"IDENTIFIED BY '{root_password}'")

        # Shutdown MySQL server
        logging.debug("Inital MySQL setup done, shutdown server..")
        Mysql.execute_statement(sql="SHUTDOWN", username="root", password=root_password)
        mysql_process.wait()

        return True

    @staticmethod
    def server_start(use_root_password=True):
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

        Mysql.wait_for_connection(password=root_password)

        return mysql_process

    @staticmethod
    def wait_for_connection(timeout=120, username='root',
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

        logging.error("Unable to connect to MySQL (timeout=%i). %s",
                      elapsed_time, last_error)
        sys.exit(1)

        return False

    @staticmethod
    def execute_statement(sql=None, username='root',
                          password=None, database='mysql'):

        """
        Execute the given SQL statement.
        """
        try:
            cnx = mysql.connector.connect(user=username, password=password,
                                          database=database,
                                          unix_socket='/var/run/mysqld/mysqld.sock')
            cursor = cnx.cursor()

            cursor.execute(sql)

            cnx.close()
            return True
        except mysql.connector.Error as err:
            logging.error("Failed to execute SQL: %s", err)
            sys.exit(1)

    @staticmethod
    def backup_data():
        """
        Backup the local MySQL Server and upload
        the backup into a S3 bucket.
        """

        # Call Setup to ensure bucket and policies do exist
        Minio.setup_connection()

        # Backup directory
        current_time = time.time()
        backup_dir = f"/tmp/mysql_backup_{current_time}"
        backup_folder_name = "mysql"
        backup_dest = f"{backup_dir}/{backup_folder_name}"

        logging.info("Backing up MySQL into dir %s", backup_dest)
        if os.path.exists(backup_dir):
            logging.error("Backup path %s already exists, skipping backup run", backup_dest)

        # Crate backup dir
        os.makedirs(backup_dir)

        # Create mysql backup
        backup_user = os.environ.get("MYSQL_BACKUP_USER")
        backup_password = os.environ.get("MYSQL_BACKUP_PASSWORD")
        xtrabackup = ["/usr/bin/xtrabackup", f"--user={backup_user}",
                      f"--password={backup_password}", "--backup",
                      f"--target-dir={backup_dest}"]

        subprocess.run(xtrabackup, check=True)

        # Prepare backup
        xtrabackup_prepare = ["/usr/bin/xtrabackup", "--prepare",
                              f"--target-dir={backup_dest}"]

        subprocess.run(xtrabackup_prepare, check=True)

        # Compress backup (structure in tar mysql/*)
        backup_file = f"/tmp/mysql_backup_{current_time}.tgz"
        tar = ["/bin/tar", "zcf", backup_file, "-C", backup_dir, backup_folder_name]
        subprocess.run(tar, check=True)

        # Upload Backup to S3 Bucket
        mc_args = ["/usr/local/bin/mc", "cp", backup_file, "backup/mysqlbackup/"]
        subprocess.run(mc_args, check=True)

        # Remove old backup data
        rmtree(backup_dir)
        os.remove(backup_file)

        logging.info("Backup was successfully created")

    @staticmethod
    def restore_data():
        """
        Restore the latest MySQL dump from the S3 Bucket
        """
        logging.info("Restore MySQL Backup")

        backup_file = Minio.get_latest_backup_file()

        if backup_file is None:
            logging.error("Unable to restore backup, no backup found in bucket")
            return False

        # Restore directory
        current_time = time.time()
        restore_dir = f"/tmp/mysql_restore_{current_time}"

        mc_download = ["/usr/local/bin/mc", "cp", f"backup/mysqlbackup/{backup_file}", restore_dir]
        subprocess.run(mc_download, check=True)

        # Shutdown MySQL
        # rm -r /var/lib/mysql/*
        # xtrabackup --copy-back --target-dir=/tmp/tmp/mysql_backup_1605027555.6030998/
        # chown mysql.mysql -R /var/lib/mysql/
        # Start MySQL

        # Remove old backup data
        rmtree(restore_dir)
        return True
