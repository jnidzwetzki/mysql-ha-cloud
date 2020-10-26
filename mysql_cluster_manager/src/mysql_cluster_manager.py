#!/usr/bin/env python3

import time
import argparse

parser = argparse.ArgumentParser(description='MySQL cluster manager.')

parser.add_argument('operation', metavar='operation', help='Operation to be executed')

args = parser.parse_args()

if args.operation == 'join_or_bootstrap':
    while True:
        time.sleep(1)
else:
    print(f"Unknown operation: {args.operation}");
    exit(1)

