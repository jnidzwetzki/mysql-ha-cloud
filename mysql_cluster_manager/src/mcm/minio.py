import os
import logging
import subprocess

class Minio:

    @staticmethod
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
        mc_set_policy_bucket = ["mc", "ilm", "set", "--id=expire_rule",
                                "-expiry-days=7", bucket_name]
        subprocess.run(mc_set_policy_bucket, check=True)

    @staticmethod
    def minio_get_latest_backup_file():
        """
        Get the latest backup filename from the bucket
        """
        # Call Setup to ensure bucket and connection do exist
        Minio.minio_setup()

        logging.debug("Searching for latest MySQL Backup")
        mc_search = ["/usr/local/bin/mc", "find", "backup/mysqlbackup/", "--name",
                     "mysql*.tgz", "-print", "{time} # {base}"]

        # mc find backup/mysqlbackup/ --name "mysql*.tgz" -print '{time} # {base}'
        # 2020-11-08 08:42:12 UTC - mysql_backup_1604824911.437146.tgz
        # 2020-11-08 08:50:53 UTC - mysql_backup_1604825437.6691067.tgz
        # 2020-11-08 08:55:03 UTC - mysql_backup_1604825684.9835322.tgz

        process = subprocess.run(mc_search, check=True, capture_output=True)
        files = process.stdout.splitlines()

        if not files:
            logging.debug("S3 Bucket is empty")
            return None

        # Take the newest file
        newest_file = files[-1]
        changedate, filename = newest_file.decode().split("#")

        # Remove empty chars after split
        changedate = changedate.strip()
        filename = filename.strip()

        logging.debug("Newest backup file '%s', date '%s'", filename, changedate)

        return filename
