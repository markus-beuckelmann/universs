#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from flask import Flask
from celery import Celery

app = Flask('universs')

# Celery configuration
# app.config['CELERY_BROKER_URL'] = 'mongodb://localhost:27017/celery'
# app.config['CELERY_RESULT_BACKEND'] = 'mongodb'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379'

DEFAULT_PAGE_LIMIT = 100
DEFAULT_SORT = 'date'
TIMEZONE = 'Europe/Berlin'
TIMEFORMAT = '%d.%m.%Y, %H:%M:%S Uhr (%Z)'
# Set this to 'unread' to only show unread articles by default
SHOW_ONLY_UNREAD = 'unread'

# Celery
celery = Celery(app.import_name, backend = app.config['CELERY_RESULT_BACKEND'], broker = app.config['CELERY_BROKER_URL'])

# Import custom Jinja2 filters
import universs.filters

# Now import the views...
import universs.views
