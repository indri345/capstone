# Gunakan base image Python resmi yang stabil
FROM python:3.10-slim

# Atur environment variabel agar Python tidak menulis file .pyc dan output langsung muncul di log
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Buat folder kerja di dalam server
WORKDIR /app

# Install dependensi sistem yang dibutuhkan untuk library Python (seperti psycopg2 untuk PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements dan install seluruh library
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy seluruh file proyek Anda ke dalam server
COPY . /app/

# Pindahkan pemanggilan entrypoint.sh setelah semua file tersalin ke /app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# HAPUS EXPOSE 7860 karena Railway menggunakan port dinamis dari variabel $PORT

# Jalankan skrip saat kontainer pertama kali dinyalakan
ENTRYPOINT ["/app/entrypoint.sh"]
