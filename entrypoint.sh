#!/bin/sh

# 1. Jalankan pengumpulan file statis
python manage.py collectstatic --no-input

# 2. Jalankan migrasi database PostgreSQL
python manage.py migrate --no-input

# 3. Nyalakan server Gunicorn dengan port dinamis Railway
exec gunicorn digital_culture.wsgi:application --bind 0.0.0.0:$PORT
