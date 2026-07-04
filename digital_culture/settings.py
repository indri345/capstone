"""
Django settings for digital_culture project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env in development
dotenv_root = BASE_DIR / '.env'
dotenv_cms = BASE_DIR / 'cms' / '.env'
load_dotenv(dotenv_root)
load_dotenv(dotenv_cms, override=False)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-fallback-only-for-local-dev-do-not-use-in-production',
)

# SECURITY WARNING: don't run with debug turned on in production!
# Default ke False sekarang — kalau DEBUG env var tidak di-set di server
# (misal lupa di-set di Railway), aplikasi tetap production-safe by default.
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('1', 'true', 'yes')

# ALLOWED_HOSTS diambil dari environment variable, dipisah koma.
# Contoh di .env / Railway variables:
#   ALLOWED_HOSTS=digitalculture.up.railway.app,127.0.0.1,localhost
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'digital_culture.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'digital_culture.wsgi.application'


# Database
if 'DATABASE_URL' in os.environ:
    # KODE INI BERJALAN SAAT DI RAILWAY
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600)
    }
else:
    # KODE INI BERJALAN SAAT DI LAPTOP KAMU
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'capstone_db'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Only use manifest static files storage when explicitly enabled in a
# production-like environment. Local development can keep DEBUG=False
# without requiring collectstatic or a manifest file.
use_manifest_staticfiles = os.environ.get('USE_MANIFEST_STATICFILES', 'False').lower() in ('1', 'true', 'yes')
if DEBUG or not use_manifest_staticfiles:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CSRF_TRUSTED_ORIGINS = [
    'https://*.up.railway.app',
    'https://web-production-36aaf.up.railway.app',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
