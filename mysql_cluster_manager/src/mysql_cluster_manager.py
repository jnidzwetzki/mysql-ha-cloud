#!/usr/bin/env python3

"""This file is part of the MySQL cluster manager"""

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

args = parser.parse_args()

logging.basicConfig(level=args.log_level,
                    format='%(levelname)s %(name)s %(message)s')

if args.operation == 'join_or_bootstrap':
    Actions.join_or_bootstrap()
elif args.operation == 'mysql_backup':
    Mysql.backup_data()
elif args.operation == 'mysql_restore':
    Mysql.restore_data()
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
