#!/bin/sh
mkdir -p /data/web/static /data/web/media
chmod -R 755 /data/web/static /data/web/media
exec "$@"
