"""This file is part of the MySQL cluster manager"""

import os
import logging
import datetime
import subprocess

class Minio:
    """
    This class encapsulates all Minio related things
    """

    minio_binary = "/usr/local/bin/mc"

    @staticmethod
    def setup_connection():
        """
        Setup the MinIO agent.
        """

        logging.info("Setup MinIO agent")

        minio_url = os.environ.get("MINIO_URL")
        minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
        minio_secret_key = os.environ.get("MINIO_SECRET_KEY")

        bucket_name = "backup/mysqlbackup"

        # Register server
        mc_args = [Minio.minio_binary, "alias", "set", "backup",
                   minio_url, minio_access_key, minio_secret_key]
        subprocess.run(mc_args, check=True)

        # Create bucket
        mc_create_bucket = [Minio.minio_binary, "mb", bucket_name, "-p"]
        subprocess.run(mc_create_bucket, check=True)

        # Set expire policy on bucket
        mc_set_policy_bucket = [Minio.minio_binary, "ilm", "edit", "--id=expire_rule",
                                "-expiry-days=7", bucket_name]
        subprocess.run(mc_set_policy_bucket, check=True)

    @staticmethod
    def get_backup_info():
        """
        Get the information about backups
        """
        # Call Setup to ensure bucket and connection do exist
        Minio.setup_connection()

        logging.debug("Searching for latest MySQL Backup")
        mc_search = [Minio.minio_binary, "find", "backup/mysqlbackup/", "--name",
                     "mysql*.tgz", "-print", "{time} # {base}"]

        # mc find backup/mysqlbackup/ --name "mysql*.tgz" -print '{time} # {base}'
        # 2020-11-08 08:42:12 UTC # mysql_backup_1604824911.437146.tgz
        # 2020-11-08 08:50:53 UTC # mysql_backup_1604825437.6691067.tgz
        # 2020-11-08 08:55:03 UTC # mysql_backup_1604825684.9835322.tgz

        process = subprocess.run(mc_search, check=True, capture_output=True)
        files = process.stdout.splitlines()

        return files

    @staticmethod
    def does_backup_exists():
        """
        Does a old backups exists?
        """
        files = Minio.get_backup_info()

        if not files:
            logging.debug("S3 Bucket is empty")
            return False

        return True

    @staticmethod
    def get_latest_backup():
        """
        Get the latest backup filename from the bucket
        """
        files = Minio.get_backup_info()

        newest_changedate = None
        newest_file = None

        # Take the newest file
        for element in files:
            element_changedate, element_filename = element.decode().split("#")

            # Remove empty chars after split
            element_changedate = element_changedate.strip()
            element_filename = element_filename.strip()

            element_change_date = datetime.datetime.strptime(element_changedate,
                                                             '%Y-%m-%d %H:%M:%S UTC')

            if (newest_changedate is None) or (element_change_date > newest_changedate):
                newest_changedate = element_change_date
                newest_file = element_filename

        logging.debug("Newest backup file '%s', date '%s'", newest_file, newest_changedate)

        return (newest_file, newest_changedate)
