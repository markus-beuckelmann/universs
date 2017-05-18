#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from flask import Flask
from flask import g

from base import init as dbinit

app = Flask(__name__)

@app.before_request
def init():

    g.db = db = dbinit()
    g.feeds = list(db.feeds.find())
    g.tags = list(db.tags.find())
    g.agents = list(db.agents.find())
    g.filters = list(db.filters.find())

if __name__ == '__main__':

    app.run(debug = True)
