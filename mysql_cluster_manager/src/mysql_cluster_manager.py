#!/usr/bin/env python3

import os
import sys
import time
import argparse
import subprocess

parser = argparse.ArgumentParser(description='MySQL cluster manager.')

parser.add_argument('operation', metavar='operation', help='Operation to be executed')

args = parser.parse_args()

if args.operation == 'join_or_bootstrap':

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

    consul_process = subprocess.run(consul_args, capture_output=False, check=True)

    while True:
        time.sleep(1)
else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
