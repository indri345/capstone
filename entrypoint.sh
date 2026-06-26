#!/bin/sh

# Jalankan migrasi database
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# GANTI PAKE INI (Sesuaikan 'nama_project_kamu' dengan folder wsgi.py berada)
exec gunicorn digital_culture.wsgi:application --bind 0.0.0.0:$PORT
