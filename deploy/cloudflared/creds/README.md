# Cloudflare Tunnel credentials

Place the Cloudflare Tunnel credentials JSON file here.

Expected layout:

- `your-tunnel-uuid.json`
- `config.yml`
- `run-tunnel.sh`

The compose file mounts this directory at `/etc/cloudflared/creds` inside the container.
