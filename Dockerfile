# Gunakan base image Python resmi yang stabil
FROM python:3.10-slim

# Atur environment variabel agar Python tidak menulis file .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Buat folder kerja di dalam server
WORKDIR /app

# Install dependensi sistem yang dibutuhkan untuk beberapa library Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements dan install seluruh library (termasuk transformers)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh file proyek Anda ke dalam server
COPY . /app/

# Jalankan perintah kumpulkan file statis Django
RUN python manage.py collectstatic --noinput

# Buka port 7860 (Port khusus yang wajib digunakan di Hugging Face Spaces)
EXPOSE 7860

# Jalankan aplikasi Django menggunakan Gunicorn pada port 7860
CMD python manage.py migrate --no-input && gunicorn digital_culture.wsgi:application --bind 0.0.0.0:$PORT
