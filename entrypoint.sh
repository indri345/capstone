#!/bin/sh

# Jalankan migrasi database (opsional tapi disarankan)
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Jalankan Gunicorn (Pastikan menggunakan tanda kutip ganda atau tanpa kutip untuk $PORT)
exec gunicorn myproject.wsgi:application --bind 0.0.0.0:$PORT
