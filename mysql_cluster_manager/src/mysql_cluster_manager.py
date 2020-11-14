#!/usr/bin/env python3

"""This file is part of the MySQL cluster manager"""

import os
import sys
import logging
import argparse

from mcm.actions import Actions
from mcm.mysql import Mysql

parser = argparse.ArgumentParser(
    description="MySQL cluster manager",
    epilog="For more info, please see: https://github.com/jnidzwetzki/mysql-ha-cloud")

AVAILABLE_OPERATIONS = "(join_or_bootstrap, mysql_backup, mysql_restore)"
parser.add_argument('operation', metavar='operation',
                    help=f'Operation to be executed {AVAILABLE_OPERATIONS}')

log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
parser.add_argument('--log-level', default='INFO', choices=log_levels)

# Parse args
args = parser.parse_args()

# Configure logging
logging.basicConfig(level=args.log_level,
                    format='%(levelname)s %(name)s %(message)s')

# Check for all needed env vars
required_envvars = ['CONSUL_BIND_INTERFACE', 'CONSUL_BOOTSTRAP_SERVER',
                    'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY', 'MINIO_URL',
                    'MYSQL_ROOT_PASSWORD', 'MYSQL_BACKUP_USER', 'MYSQL_BACKUP_PASSWORD',
                    'MYSQL_REPLICATION_USER', 'MYSQL_REPLICATION_PASSWORD']

for required_var in required_envvars:
    if not required_var in os.environ:
        logging.error("Required environment %s not found, exiting", required_var)
        sys.exit(1)

# Perform operations
if args.operation == 'join_or_bootstrap':
    Actions.join_or_bootstrap()
elif args.operation == 'mysql_backup':
    Mysql.backup_data()
elif args.operation == 'mysql_restore':
    Mysql.restore_data()
else:
    logging.error("Unknown operation: %s", {args.operation})
    sys.exit(1)
