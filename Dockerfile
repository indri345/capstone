FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Jalankan migrasi database langsung di sini saat container dinyalakan, 
# kemudian langsung jalankan gunicorn menggunakan shell form (tanpa tanda kurung siku) 
# agar $PORT bisa dibaca sempurna oleh Railway.
CMD python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn digital_culture.wsgi:application --bind 0.0.0.0:$PORT
