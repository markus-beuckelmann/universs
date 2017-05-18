#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from flask import Flask
from base import init as dbinit

app = Flask(__name__)

if __name__ == '__main__':

    app.run(debug = True)
