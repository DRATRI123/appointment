#!/bin/sh
# certbot renews certificates in its own container (no Docker socket is shared with it), so Nginx re-reads them
# itself every 6 hours. A reload is graceful: open connections finish normally.
set -eu
(
    while sleep 21600; do
        nginx -t -q && nginx -s reload
    done
) &
