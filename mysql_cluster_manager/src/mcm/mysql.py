"""This file is part of the MySQL cluster manager"""

import os
import sys
import time
import shutil
import logging
import threading
import subprocess

from shutil import rmtree
from datetime import timedelta

import mysql.connector

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.utils import Utils

class Mysql:

    """
    This class encapsulates all MySQL related things
    """

    xtrabackup_binary = "/usr/bin/xtrabackup"
    mysql_server_binary = "/usr/bin/mysqld_safe"
    mysqld_binary = "/usr/sbin/mysqld"
    mysql_datadir = "/var/lib/mysql"

    @staticmethod
    def init_database_if_needed():
        """
        Init a MySQL and configure permissions.
        """

        logging.info("Init MySQL database directory")

        if os.path.isfile(f"{Mysql.mysql_datadir}/ib_logfile0"):
            logging.info("MySQL is already initialized, skipping")
            return False

        mysql_init = [Mysql.mysqld_binary, "--initialize-insecure", "--user=mysql"]

        subprocess.run(mysql_init, check=True)

        # Start server the first time
        mysql_process = Mysql.server_start(use_root_password=False)

        # Create application user
        logging.debug("Creating MySQL user for the application")
        application_user = os.environ.get("MYSQL_APPLICATION_USER")
        appication_password = os.environ.get("MYSQL_APPLICATION_PASSWORD")

        # Password needs to be mysql_native_password for ProxySQL
        # See https://github.com/sysown/proxysql/issues/2580
        Mysql.execute_statement_or_exit(f"CREATE USER '{application_user}'@'localhost' "
                                        f"IDENTIFIED WITH mysql_native_password BY '{appication_password}'")
        Mysql.execute_statement_or_exit(f"GRANT ALL PRIVILEGES ON *.* TO '{application_user}'@'localhost'")
        Mysql.execute_statement_or_exit(f"CREATE USER '{application_user}'@'%' "
                                        f"IDENTIFIED WITH mysql_native_password BY '{appication_password}'")
        Mysql.execute_statement_or_exit(f"GRANT ALL PRIVILEGES ON *.* TO '{application_user}'@'%'")

        # Create backup user
        logging.debug("Creating MySQL user for backups")
        backup_user = os.environ.get("MYSQL_BACKUP_USER")
        backup_password = os.environ.get("MYSQL_BACKUP_PASSWORD")
        Mysql.execute_statement_or_exit(f"CREATE USER '{backup_user}'@'localhost' "
                                        f"IDENTIFIED BY '{backup_password}'")
        Mysql.execute_statement_or_exit("GRANT BACKUP_ADMIN, PROCESS, RELOAD, LOCK TABLES, "
                                        f"REPLICATION CLIENT ON *.* TO '{backup_user}'@'localhost'")
        Mysql.execute_statement_or_exit("GRANT SELECT ON performance_schema.log_status TO "
                                        f"'{backup_user}'@'localhost'")

        # Create replication user
        logging.debug("Creating replication user")
        replication_user = os.environ.get("MYSQL_REPLICATION_USER")
        replication_password = os.environ.get("MYSQL_REPLICATION_PASSWORD")
        Mysql.execute_statement_or_exit(f"CREATE USER '{replication_user}'@'%' "
                                        f"IDENTIFIED BY '{replication_password}'")
        Mysql.execute_statement_or_exit("GRANT REPLICATION SLAVE ON *.* TO "
                                        f"'{replication_user}'@'%'")

        # Change permissions for the root user
        logging.debug("Set permissions for the root user")
        root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
        Mysql.execute_statement_or_exit(f"CREATE USER 'root'@'%' IDENTIFIED BY '{root_password}'")
        Mysql.execute_statement_or_exit("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' "
                                        "WITH GRANT OPTION")
        Mysql.execute_statement_or_exit("ALTER USER 'root'@'localhost' "
                                        f"IDENTIFIED BY '{root_password}'")

        # Shutdown MySQL server
        logging.debug("Inital MySQL setup done, shutdown server..")
        Mysql.execute_statement_or_exit(sql="SHUTDOWN", username="root", password=root_password)
        mysql_process.wait()

        return True

    @staticmethod
    def build_configuration():
        """
        Build the MySQL server configuratuion.
        """
        consul = Consul.get_instance()
        server_id = consul.get_mysql_server_id()

        outfile = open("/etc/mysql/conf.d/zz_cluster.cnf", 'w')
        outfile.write("# DO NOT EDIT - This file was generated automatically\n")
        outfile.write("[mysqld]\n")
        outfile.write(f"server_id={server_id}\n")
        outfile.write("gtid_mode=ON\n")
        outfile.write("enforce-gtid-consistency=ON\n")
        outfile.close()

    @staticmethod
    def change_to_replication_client(leader_ip):
        """
        Make the local MySQL installation to a replication follower
        """

        logging.info("Setting up replication (leader=%s)", leader_ip)

        replication_user = os.environ.get("MYSQL_REPLICATION_USER")
        replication_password = os.environ.get("MYSQL_REPLICATION_PASSWORD")

        Mysql.execute_query_as_root("STOP SLAVE", discard_result=True)

        Mysql.execute_query_as_root(f"CHANGE MASTER TO MASTER_HOST = '{leader_ip}', "
                                    f"MASTER_PORT = 3306, MASTER_USER = '{replication_user}', "
                                    f"MASTER_PASSWORD = '{replication_password}', "
                                    "MASTER_AUTO_POSITION = 1, GET_MASTER_PUBLIC_KEY = 1"
                                    , discard_result=True)

        Mysql.execute_query_as_root("START SLAVE", discard_result=True)

        # Set replicia to read only
        logging.info("Set MySQL-Server mode to read-only")
        Mysql.execute_query_as_root("SET GLOBAL read_only = 1", discard_result=True)
        Mysql.execute_query_as_root("SET GLOBAL super_read_only = 1", discard_result=True)

    @staticmethod
    def delete_replication_config():
        """
        Stop the replication
        """
        logging.debug("Removing old replication configuraion")
        Mysql.execute_query_as_root("STOP SLAVE", discard_result=True)
        Mysql.execute_query_as_root("RESET SLAVE ALL", discard_result=True)

        # Accept writes
        logging.info("Set MySQL-Server mode to read-write")
        Mysql.execute_query_as_root("SET GLOBAL super_read_only = 0", discard_result=True)
        Mysql.execute_query_as_root("SET GLOBAL read_only = 0", discard_result=True)

    @staticmethod
    def get_replication_leader_ip():
        """
        Get the current replication leader ip
        """
        slave_status = Mysql.execute_query_as_root("SHOW SLAVE STATUS")

        if len(slave_status) != 1:
            return None

        if not 'Master_Host' in slave_status[0]:
            logging.error("Invalid output, master_host not found %s", slave_status)
            return None

        return slave_status[0]['Master_Host']

    @staticmethod
    def is_repliation_data_processed():
        """
        Is the repliation log from the master completely processed
        """

        slave_status = Mysql.execute_query_as_root("SHOW SLAVE STATUS")

        if len(slave_status) != 1:
            return False

        if not 'Slave_IO_State' in slave_status[0]:
            logging.error("Invalid output, Slave_IO_State not found %s", slave_status)
            return False

        # Leader is sending data
        io_state = slave_status[0]['Slave_IO_State']
        logging.debug("Follower IO state is '%s'", io_state)
        if io_state != "Waiting for master to send event":
            return False

        if not 'Slave_SQL_Running_State' in slave_status[0]:
            logging.error("Invalid output, Slave_SQL_Running_State not found %s", slave_status)
            return False

        # Data is not completely proessed
        sql_state = slave_status[0]['Slave_SQL_Running_State']
        logging.debug("Follower SQL state is '%s'", sql_state)
        if sql_state != "Slave has read all relay log; waiting for more updates":
            return False

        return True

    @staticmethod
    def server_start(use_root_password=True):
        """
        Start the MySQL server and wait for ready to serve connections.
        """

        logging.info("Starting MySQL")

        Mysql.build_configuration()

        mysql_server = [Mysql.mysql_server_binary, "--user=mysql"]
        mysql_process = subprocess.Popen(mysql_server)

        # Use root password for the connection or not
        root_password = None
        if use_root_password:
            root_password = os.environ.get("MYSQL_ROOT_PASSWORD")

        Mysql.wait_for_connection(password=root_password)

        return mysql_process

    @staticmethod
    def server_stop():
        """
        Stop the MySQL server.
        """
        logging.info("Stopping MySQL Server")

        # Try to shutdown the server without a password
        result = Mysql.execute_statement(sql="SHUTDOWN", log_error=False)

        # Try to shutdown the server using the root password
        if not result:
            root_password = os.environ.get("MYSQL_ROOT_PASSWORD")
            Mysql.execute_statement(sql="SHUTDOWN", password=root_password)

    @staticmethod
    def execute_query_as_root(sql, database='mysql', discard_result=False):
        """
        Execute the SQL query and return result.
        """

        root_password = os.environ.get("MYSQL_ROOT_PASSWORD")

        cnx = None

        try:
            cnx = mysql.connector.connect(user='root', password=root_password,
                                          database=database,
                                          unix_socket='/var/run/mysqld/mysqld.sock')


            cur = cnx.cursor(dictionary=True, buffered=True)
            cur.execute(sql)

            if discard_result:
                return None

            return cur.fetchall()
        finally:
            if cnx:
                cnx.close()

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
    def execute_statement_or_exit(sql=None, username='root',
                                  password=None, database='mysql',
                                  port=None):

        """
        Execute the given SQL statement.
        """
        result = Mysql.execute_statement(sql=sql, username=username, port=port,
                                         password=password, database=database)
        if not result:
            sys.exit(1)

    @staticmethod
    def execute_statement(sql=None, username='root',
                          password=None, database='mysql',
                          port=None, log_error=True):
        """
        Execute the given SQL statement.
        """
        try:
            if port is None:
                cnx = mysql.connector.connect(user=username, password=password,
                                              database=database,
                                              unix_socket='/var/run/mysqld/mysqld.sock')

            else:
                cnx = mysql.connector.connect(user=username, password=password,
                                              database=database, port=port)

            cursor = cnx.cursor()

            cursor.execute(sql)

            cnx.close()
            return True
        except mysql.connector.Error as err:
            if log_error:
                logging.error("Failed to execute SQL: %s", err)
            return False

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
        xtrabackup = [Mysql.xtrabackup_binary, f"--user={backup_user}",
                      f"--password={backup_password}", "--backup",
                      f"--target-dir={backup_dest}"]

        subprocess.run(xtrabackup, check=True)

        # Prepare backup
        xtrabackup_prepare = [Mysql.xtrabackup_binary, "--prepare",
                              f"--target-dir={backup_dest}"]

        subprocess.run(xtrabackup_prepare, check=True)

        # Compress backup (structure in tar mysql/*)
        backup_file = f"/tmp/mysql_backup_{current_time}.tgz"
        tar = ["/bin/tar", "zcf", backup_file, "-C", backup_dir, backup_folder_name]
        subprocess.run(tar, check=True)

        # Upload Backup to S3 Bucket
        mc_args = [Minio.minio_binary, "cp", backup_file, "backup/mysqlbackup/"]
        subprocess.run(mc_args, check=True)

        # Remove old backup data
        rmtree(backup_dir)
        os.remove(backup_file)

        logging.info("Backup was successfully created")

    @staticmethod
    def create_backup_if_needed(maxage_seconds=60*60*6):
        """
        Create a new backup if needed. Default age is 6h
        """
        logging.debug("Checking for backups")

        consul_client = Consul.get_instance()
        if not consul_client.is_replication_leader():
            logging.debug("We are not the replication master, skipping backup check")
            return False

        backup_name, backup_date = Minio.get_latest_backup()

        if Utils.is_refresh_needed(backup_date, timedelta(seconds=maxage_seconds)):
            logging.info("Old backup is outdated (%s, %s), creating new one",
                         backup_name, backup_date)

            # Perform backup in extra thread to prevent Consul loop interruption
            backup_thread = threading.Thread(target=Mysql.backup_data)
            backup_thread.start()

            return True

        return False

    @staticmethod
    def restore_backup():
        """
        Restore the latest MySQL dump from the S3 Bucket
        """
        logging.info("Restore MySQL Backup")
        current_time = time.time()

        if os.path.isfile(f"{Mysql.mysql_datadir}/ib_logfile0"):
            logging.info("MySQL is already initialized, cleaning up first")
            old_mysql_dir = f"{Mysql.mysql_datadir}_old_{current_time}"

            os.mkdir(old_mysql_dir, 0o700)

            # Renaming file per file, on some docker images
            # the complete directory can not be moved
            for entry in os.listdir(Mysql.mysql_datadir):
                source_name = f"{Mysql.mysql_datadir}/{entry}"
                dest_name = f"{old_mysql_dir}/{entry}"
                logging.debug("Moving %s to %s", source_name, dest_name)
                shutil.move(source_name, dest_name)

            logging.info("Old MySQL data moved to: %s", old_mysql_dir)


        backup_file, _ = Minio.get_latest_backup()

        if backup_file is None:
            logging.error("Unable to restore backup, no backup found in bucket")
            return False

        # Restore directory
        restore_dir = f"/tmp/mysql_restore_{current_time}"

        # Crate restore dir
        os.makedirs(restore_dir)

        # Download backup
        mc_download = [Minio.minio_binary, "cp", f"backup/mysqlbackup/{backup_file}",
                       restore_dir]
        subprocess.run(mc_download, check=True)

        # Unpack backup
        tar = ["/bin/tar", "zxf", f"{restore_dir}/{backup_file}", "-C", restore_dir]
        subprocess.run(tar, check=True)

        # Ensure that this is a MySQL Backup
        if not os.path.isfile(f"{restore_dir}/mysql/ib_logfile0"):
            logging.error("Unpacked backup is not a MySQL backup")
            rmtree(restore_dir)
            return False

        # Restore backup
        xtrabackup = [Mysql.xtrabackup_binary, "--copy-back",
                      f"--target-dir={restore_dir}/mysql"]
        subprocess.run(xtrabackup, check=True)

        # Change permissions of the restored data
        chown = ['chown', 'mysql.mysql', '-R', '/var/lib/mysql/']
        subprocess.run(chown, check=True)

        # Remove old backup data
        rmtree(restore_dir)
        return True


    @staticmethod
    def restore_backup_or_exit():
        """
        Restore a backup or exit
        """

        result = Mysql.restore_backup()

        if not result:
            logging.error("Unable to restore MySQL backup")
            sys.exit(1)
