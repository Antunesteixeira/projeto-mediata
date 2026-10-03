#!/bin/sh
set -eu
mkdir -p "$HOME"
python manage.py migrate --noinput
exec python manage.py runserver 0.0.0.0:8000
