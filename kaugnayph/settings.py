"""
Django settings for kaugnayph project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


# SECURITY SETTINGS

SECRET_KEY = 'django-insecure-ud(77ore(xk)a9(7c0f+83(0mtxo-%2n)k5izwbiot3kt+ysb)'

DEBUG = True

ALLOWED_HOSTS = [
    "barangaythesis.swiftlink.pro",
    "127.0.0.1",
    "localhost",
]

CSRF_TRUSTED_ORIGINS = [
    "https://barangaythesis.swiftlink.pro",
]


# APPLICATIONS

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'captcha',
]


# MIDDLEWARE

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# URLS / TEMPLATES

ROOT_URLCONF = 'kaugnayph.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'kaugnayph.wsgi.application'


# DATABASE

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'kaugnayph',
        'USER': 'barangay_user',
        'PASSWORD': 'b@ranG@y!@#',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}


# PASSWORD VALIDATION

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# INTERNATIONALIZATION

LANGUAGE_CODE = 'en'

LANGUAGES = [
    ('en', 'English'),
    ('tl', 'Tagalog'),
]

USE_I18N = True

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'Asia/Manila'

USE_I18N = True

USE_TZ = True


# STATIC FILES

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / "static",
]


# SMS SETTINGS

SMS_URL = os.getenv("SMS_URL")
SMS_USERNAME = os.getenv("SMS_USERNAME")
SMS_PASSWORD = os.getenv("SMS_PASSWORD")
SMS_PROVIDER = os.getenv("SMS_PROVIDER")

# EMAIL SETTINGS

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 465))

EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# DEFAULT PRIMARY KEY

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Session Expiration Settings
SESSION_COOKIE_AGE = 3600             # 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True     # Refresh session on activity
SESSION_COOKIE_SECURE = not DEBUG     # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True        # Prevent JS access
SESSION_COOKIE_SAMESITE = 'Lax'
LOGIN_URL = '/login/'

# File uploads
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Max upload size: 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# OPENAI / CONTENT MODERATION
load_dotenv() 
OPENAI_API_KEY = os.getenv("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")