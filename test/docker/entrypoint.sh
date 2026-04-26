#!/bin/bash
set -e

# Start SSH daemon
/etc/init.d/ssh start

# Run the original WordPress entrypoint
exec docker-entrypoint.sh "$@"
