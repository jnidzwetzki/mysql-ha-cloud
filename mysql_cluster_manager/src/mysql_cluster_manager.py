#!/usr/bin/env python3

"""This file is part of the MySQL cluster manager"""

import sys
import time
import logging
import argparse

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.mysql import Mysql

parser = argparse.ArgumentParser(
    description="MySQL cluster manager",
    epilog="For more info, please see: https://github.com/jnidzwetzki/mysql-ha-cloud")

AVAILABLE_OPERATIONS = "(join_or_bootstrap, mysql_backup, mysql_restore)"
parser.add_argument('operation', metavar='operation',
                    help=f'Operation to be executed {AVAILABLE_OPERATIONS}')

log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
parser.add_argument('--log-level', default='INFO', choices=log_levels)

def join_or_bootstrap():
    """
    Join the existing cluster or bootstrap a new cluster
    """

    Minio.setup_connection()
    consul_process = Consul.agent_start()

    # Check if we have an existing backup to restore
    # Use this backup if exists, or init a new MySQL database
    last_backup = Minio.get_latest_backup_file()

    if last_backup is None:
        result = Mysql.init_database()

        if not result:
            logging.error("Unable to init MySQL database")
            sys.exit(1)
    else:
        result = Mysql.restore_data()

        if not result:
            logging.error("Unable to restore MySQL backup")
            sys.exit(1)

    Consul.setup_connection()
    mysql_process = Mysql.server_start()

    while True:
        consul_process.poll()
        mysql_process.poll()
        time.sleep(1)




args = parser.parse_args()

logging.basicConfig(level=args.log_level,
                    format='%(levelname)s %(name)s %(message)s')

if args.operation == 'join_or_bootstrap':
    join_or_bootstrap()
elif args.operation == 'mysql_backup':
    Mysql.backup_data()
elif args.operation == 'mysql_restore':
    Mysql.restore_data()
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
