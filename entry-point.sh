#!/bin/bash
#
# Start the MySQL cluster manager 
#
########################

# Exit on error
set -e

./mysql_cluster_manager.py join_or_bootstrap
