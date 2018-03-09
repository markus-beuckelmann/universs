#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import html

from pytz import timezone
from universs import TIMEZONE, TIMEFORMAT

# Import the Flask app
from universs import app

@app.template_filter('dt')
def _jinja2_filter_dt(date):

    date = date.replace(tzinfo = timezone('UTC'))
    date = date.astimezone(timezone(TIMEZONE))
    return date.strftime(TIMEFORMAT)

@app.template_filter('unescape')
def _jinja2_filter_unescape(value):
    return html.unescape(value)
