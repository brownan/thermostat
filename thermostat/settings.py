"""
Django settings for thermostat project.

Generated by 'django-admin startproject' using Django 3.1.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'sc+3gz2g6a^z45#%^wt6rb!!@vxm!pveld9qf*x9r5p9%1r=e)'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    #'django.contrib.admin',
    #'django.contrib.auth',
    #'django.contrib.contenttypes',
    #'django.contrib.sessions',
    #'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    #'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    #'django.contrib.auth.middleware.AuthenticationMiddleware',
    #'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'thermostat.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                #'django.contrib.auth.context_processors.auth',
                #'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'thermostat.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_URL = '/static/'

ASGI_APPLICATION = 'thermostat.routing.application'

import sys
STDERR_ISATTY = sys.stderr.isatty() if hasattr(sys.stderr, "isatty") else sys.__stderr__.isatty()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    "formatters": {
        "color": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(levelname)-8s%(reset)s [%(name)s] "
                      "%(message)s",
            "log_colors": {"DEBUG": "cyan",
                           "INFO": "white",
                           "WARNING": "yellow",
                           "ERROR": "red",
                           "CRITICAL": "white,bg_red",
                           }
        },
        "nocolor": {
            "format": "%(asctime)s %(levelname)-8s [%(name)s] "
                      "%(message)s",
            "datefmt": '%Y-%m-%d %H:%M:%S',
        },
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "color" if STDERR_ISATTY else "nocolor",
        },
    },
    "loggers": {
        "django": {
            # Django logs everything it does under this handler. We want
            # the level to inherit our root logger level and handlers,
            # but also add a mail-the-admins handler if an error comes to this
            # point (Django sends an ERROR log for unhandled exceptions in
            # views)
            "level": "NOTSET",
        },
        "django.db": {
            # Set to DEBUG to see all database queries as they happen.
            # Django only sends these messages if settings.DEBUG is True
            "level": "INFO",
        },
        "py.warnings": {
            # This is a built-in Python logger that receives warnings from
            # the warnings module and emits them as WARNING log messages*. By
            # default, this logger prints to stderr. We override that here so
            # that it simply inherits the root logger's handlers
            #
            # * Django enables this behavior by calling
            #   https://docs.python.org/3.5/library/logging.html#logging.captureWarnings
        },
        "thermostat": {
            "level": "DEBUG" if DEBUG else "INFO",
        },
    },
    "root": {
        "handlers": ["stderr"],
        "level": "INFO" if DEBUG else "WARNING",
    },
}