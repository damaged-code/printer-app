#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Run with sudo: sudo ./update.sh"; exit 1; fi
SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=${PRINTAPP_INSTALL_DIR:-/opt/home-printer}
test -f /etc/home-printer.env || { echo "Home Printer is not installed."; exit 1; }
install -m 0644 "$SOURCE_DIR/app.py" "$SOURCE_DIR/requirements.txt" "$SOURCE_DIR/jobattrs.test" "$APP_DIR/"
if [[ -f "$SOURCE_DIR/HomePrinter.ipa" ]]; then install -m 0644 "$SOURCE_DIR/HomePrinter.ipa" "$APP_DIR/"; fi
"$APP_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements.txt"
systemctl restart home-printer
systemctl --no-pager --full status home-printer
