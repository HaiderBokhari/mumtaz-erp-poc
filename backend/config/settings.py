"""
Django settings for the Mumtaz & Co Distribution ERP proof-of-concept.

This is a POC configuration: SQLite database, DEBUG on, permissive CORS.
Before any real deployment, move SECRET_KEY / DEBUG / ALLOWED_HOSTS to
environment variables and switch to Postgres.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ------------------------------------------------------------------
# Env vars below default to the original POC-local values, so nothing
# changes for local dev; only a deployment that sets them differs.

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-poc-key-change-me-before-any-real-deployment')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

# --- Applications ------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',

    # Mumtaz & Co ERP apps
    'core',
    'accounts',
    'catalog',
    'warehouses',
    'purchasing',
    'distribution',
    'accounting',
    'hr',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database ----------------------------------------------------------------
# POC default is SQLite for zero-setup local development. Setting
# DATABASE_URL (e.g. a free Neon/Supabase Postgres connection string) in
# the environment switches to Postgres without touching this file — used
# for the free hosted deployment, where SQLite's local file wouldn't
# survive a container restart.

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{os.environ.get('DJANGO_DB_PATH', BASE_DIR / 'db.sqlite3')}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalisation -----------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

# --- Static files --------------------------------------------------------------
# STATIC_URL/STATIC_ROOT serve Django's own assets (admin CSS, etc.) via
# WhiteNoise. WHITENOISE_ROOT additionally serves the built React SPA
# (frontend_dist/, produced by `npm run build`, copied in at deploy time)
# from the site root, so one Django process can serve both the API and the
# frontend in a single-URL deployment. Neither directory exists in local
# dev, which is fine — WhiteNoise just has nothing to serve there.

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if (BASE_DIR / 'frontend_dist').is_dir():
    WHITENOISE_ROOT = BASE_DIR / 'frontend_dist'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- REST framework / JWT -----------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
}

# --- CORS (POC: allow the local Vite dev server, plus any deployed origin) -----

CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
] + [origin for origin in os.environ.get('DJANGO_CORS_ALLOWED_ORIGINS', '').split(',') if origin]
CORS_ALLOW_CREDENTIALS = True

# Needed for Django admin POSTs (and any browser form) once the app is
# served over https from a host other than localhost — Django rejects
# unsafe requests whose Origin isn't in this list.
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin]

# --- Auth ----------------------------------------------------------------------

AUTH_USER_MODEL = 'auth.User'
LOGIN_REDIRECT_URL = '/admin/'

# Role names used across the app (also created as Django Groups by
# `python manage.py seed_demo_data`). Kept as a single source of truth so
# permission checks and the seed command never drift apart.
ROLE_OWNER = 'Owner'
ROLE_DISTRIBUTION_MANAGER = 'Distribution Manager'
ROLE_FSO = 'Field Sales Officer'
ROLE_SALES_MANAGER = 'Sales Manager'
ROLE_WAREHOUSE_STAFF = 'Warehouse Staff'
ROLE_DR = 'Distribution Representative'

ALL_ROLES = [
    ROLE_OWNER,
    ROLE_DISTRIBUTION_MANAGER,
    ROLE_FSO,
    ROLE_SALES_MANAGER,
    ROLE_WAREHOUSE_STAFF,
    ROLE_DR,
]
