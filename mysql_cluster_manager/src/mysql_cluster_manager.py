#!/usr/bin/env python3

import os
import sys
import time
import logging
import argparse
import subprocess

parser = argparse.ArgumentParser(description='MySQL cluster manager.')

parser.add_argument('operation', metavar='operation', help='Operation to be executed')

def start_consul_agent():
    logging.info("Starting Consul Agent")
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

    # Run process in background
    consul_process = subprocess.Popen(consul_args)

    return consul_process

def setup_minio():
    logging.info("Setup MinIO agent")

    minio_proto = os.getenv("MINIO_PROTO", "http")
    minio_server = os.environ.get("MINIO_SERVER")
    minio_port = os.getenv("MINIO_PORT", "9000")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")

    mc_args = ["mc"]
    mc_args.append("alias")
    mc_args.append("set")
    mc_args.append("backup")
    mc_args.append(f"{minio_proto}://{minio_server}:{minio_port}")
    mc_args.append(minio_access_key)
    mc_args.append(minio_secret_key)

    subprocess.run(mc_args, capture_output=True, check=True)

def setup_consul_connection():
    logging.info("Register Consul connection")

def join_or_bootstrap():
    setup_minio()
    start_consul_agent()
    setup_consul_connection()

    logging.info("Starting MySQL")
    while True:
        time.sleep(1)

args = parser.parse_args()

if args.operation == 'join_or_bootstrap':
    join_or_bootstrap()

else:
    print(f"Unknown operation: {args.operation}")
    sys.exit(1)
