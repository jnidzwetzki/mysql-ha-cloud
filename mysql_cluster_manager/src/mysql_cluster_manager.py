#!/usr/bin/env python3

import sys
import time
import logging
import argparse

from mcm.consul import Consul
from mcm.minio import Minio
from mcm.mysql import Mysql

parser = argparse.ArgumentParser(description='MySQL cluster manager.')

parser.add_argument('operation', metavar='operation', help='Operation to be executed')
log_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
parser.add_argument('--log-level', default='INFO', choices=log_levels)

def join_or_bootstrap():
    """
    Join the existing cluster or bootstrap a new cluster
    """

    Minio.minio_setup()
    consul_process = Consul.consul_agent_start()
    Mysql.mysql_init_database()
    Consul.consul_setup_connection()
    mysql_process = Mysql.mysql_start()

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
    Minio.minio_setup()
elif args.operation == 'mysql_backup':
    Mysql.mysql_backup()
elif args.operation == 'mysql_restore':
    Mysql.mysql_restore()
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
