#!/bin/sh
# Decode the install archive from the base64 file in this repo.
set -e
cd "$(dirname "$0")/.."
base64 -d packages/tiberium-0.1.1-install.zip.b64 > tiberium-0.1.1-install.zip
echo "Wrote tiberium-0.1.1-install.zip"
ls -la tiberium-0.1.1-install.zip
echo "Unpack into the root of your Horizon instance (folder with options.txt):"
echo "  unzip -o tiberium-0.1.1-install.zip -d /path/to/horizon/instance"
