#!/bin/sh
set -eu

exec cloudflared tunnel --no-autoupdate run --config /etc/cloudflared/config.yml
