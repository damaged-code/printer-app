# Home Printer

A small, private web interface and JSON API for sending PDF, PNG, and JPEG files to a CUPS printer. It supports copies, paper size, orientation, duplex printing, page ranges, job status, queue listing, and cancellation.

## Requirements

- Ubuntu or Debian with `systemd`
- A printer already configured in CUPS
- Python 3.10 or newer
- HTTPS through a reverse proxy for access outside localhost

## Install

```bash
git clone https://github.com/YOUR-NAME/home-printer.git
cd home-printer
chmod +x install.sh update.sh
sudo ./install.sh
```

The installer finds CUPS queues, asks which printer to use, asks for an app PIN, generates a session secret, creates a dedicated unprivileged service account and virtual environment, and installs a hardened systemd service. Secrets are stored in `/etc/home-printer.env` with root-only permissions.

By default the app listens on `127.0.0.1:8631`. Put Caddy, nginx, Cloudflare Tunnel, or another HTTPS proxy in front of it. If you intentionally expose it over plain HTTP on a trusted LAN, set `PRINTAPP_COOKIE_SECURE=false` in `/etc/home-printer.env`, then restart the service.

## Configuration

Edit `/etc/home-printer.env`, then run `sudo systemctl restart home-printer`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `PRINTAPP_PRINTER` | CUPS queue name | required |
| `PRINTAPP_PIN_HASH` | SHA-256 hash of the login PIN | required |
| `PRINTAPP_SECRET_KEY` | Flask session signing key | required |
| `PRINTAPP_COOKIE_SECURE` | Send session cookie over HTTPS only | `true` |
| `PRINTAPP_TRUST_PROXY` | Trust forwarded client IP headers | `false` |
| `PRINTAPP_MAX_FAILS` | Attempts before temporary lockout | `5` |
| `PRINTAPP_LOCK_SECONDS` | Lockout duration | `900` |

Generate a new PIN hash with:

```bash
printf '%s' 'your-new-pin' | sha256sum
```

## Operate and update

```bash
curl http://127.0.0.1:8631/healthz
sudo systemctl status home-printer
sudo journalctl -u home-printer -f
git pull
sudo ./update.sh
```

The optional `HomePrinter.ipa` file is intentionally excluded from Git. Copy it into the repository before installation or into `/opt/home-printer` afterward if you use the iOS download link.

## Reverse proxy example (Caddy)

```caddy
printer.example.com {
    reverse_proxy 127.0.0.1:8631
}
```

Set `PRINTAPP_TRUST_PROXY=true` only when the app is reachable exclusively through a trusted proxy.

## License

MIT
