#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo: sudo ./install.sh"
  exit 1
fi

SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=${PRINTAPP_INSTALL_DIR:-/opt/home-printer}
APP_USER=${PRINTAPP_USER:-home-printer}
APP_GROUP=$APP_USER
BIND=${PRINTAPP_BIND:-127.0.0.1:8631}
ENV_FILE=/etc/home-printer.env
SERVICE_FILE=/etc/systemd/system/home-printer.service

echo "Home Printer installer"
echo "Installing OS packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y cups cups-client python3 python3-venv
systemctl enable --now cups
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
APP_GROUP=$(id -gn "$APP_USER")

mapfile -t PRINTERS < <(lpstat -a 2>/dev/null | awk '{print $1}')
if [[ ${#PRINTERS[@]} -eq 0 ]]; then
  echo "No CUPS printer queue was found. Add one at http://localhost:631, then rerun this installer."
  exit 1
fi

DEFAULT_PRINTER=$(lpstat -d 2>/dev/null | sed 's/^system default destination: //' || true)
[[ -z "$DEFAULT_PRINTER" ]] && DEFAULT_PRINTER=${PRINTERS[0]}
echo "Available printer queues: ${PRINTERS[*]}"
read -r -p "Printer queue [$DEFAULT_PRINTER]: " PRINTER
PRINTER=${PRINTER:-$DEFAULT_PRINTER}
if ! printf '%s\n' "${PRINTERS[@]}" | grep -Fxq "$PRINTER"; then
  echo "Unknown CUPS queue: $PRINTER"
  exit 1
fi

while true; do
  read -r -s -p "Choose an app PIN (4+ characters): " PIN
  echo
  [[ ${#PIN} -ge 4 ]] && break
  echo "PIN is too short."
done

PIN_HASH=$(printf '%s' "$PIN" | sha256sum | awk '{print $1}')
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
unset PIN

echo "Installing application to $APP_DIR..."
install -d -m 0755 -o "$APP_USER" -g "$APP_GROUP" "$APP_DIR"
install -m 0644 -o "$APP_USER" -g "$APP_GROUP" "$SOURCE_DIR/app.py" "$SOURCE_DIR/requirements.txt" "$SOURCE_DIR/jobattrs.test" "$APP_DIR/"
if [[ -f "$SOURCE_DIR/HomePrinter.ipa" ]]; then
  install -m 0644 -o "$APP_USER" -g "$APP_GROUP" "$SOURCE_DIR/HomePrinter.ipa" "$APP_DIR/"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

umask 077
cat > "$ENV_FILE" <<EOF
PRINTAPP_PRINTER=$PRINTER
PRINTAPP_PIN_HASH=$PIN_HASH
PRINTAPP_SECRET_KEY=$SECRET
PRINTAPP_COOKIE_SECURE=true
PRINTAPP_TRUST_PROXY=false
EOF

sed \
  -e "s|__APP_USER__|$APP_USER|g" \
  -e "s|__APP_GROUP__|$APP_GROUP|g" \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__BIND__|$BIND|g" \
  "$SOURCE_DIR/home-printer.service" > "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable --now home-printer
sleep 1
systemctl --no-pager --full status home-printer
echo
echo "Installed successfully. Health check: http://$BIND/healthz"
echo "For direct HTTP access, set PRINTAPP_COOKIE_SECURE=false in $ENV_FILE."
