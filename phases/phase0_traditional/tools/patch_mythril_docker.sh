#!/bin/bash
# Mythril's official docker image uses an outdated version of py-solc-x
# which hardcodes 'solc-bin.ethereum.org' - a domain that was recently deleted.
# This script builds a local patched docker image that fixes the domain.

echo "Building mythril-patched docker image..."
docker build -t mythril-patched - <<EOF
FROM mythril/myth
USER root
RUN sed -i 's/solc-bin.ethereum.org/binaries.soliditylang.org/g' /usr/local/lib/python*/site-packages/solcx/install.py
USER mythril
EOF

echo "Done! You can now run Mythril evaluations."
