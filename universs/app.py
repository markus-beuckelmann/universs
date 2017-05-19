#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from flask import Flask
from flask import g, render_template

from base import init as dbinit

app = Flask(__name__)

@app.before_request
def init():

    g.db = db = dbinit()
    g.feeds = list(db.feeds.find())
    g.tags = list(db.tags.find())
    g.agents = list(db.agents.find())
    g.filters = list(db.filters.find())

@app.route('/analytics')
def analytics():

    db = g.db

    analytics = {}
    analytics['feeds-without-articles'] = []
    for feed in db.feeds.find():
        if db.articles.find({'feed-id' : feed['_id']}).count() == 0:
            analytics['feeds-without-articles'].append(feed)

    return render_template('./analytics.html', analytics = analytics, feeds = g.feeds)

@app.route('/statistics')
def statistics():

    db = g.db

    stats = {}
    stats['number-of-feeds'] = db.feeds.count()
    stats['number-of-articles'] = db.articles.count()
    stats['number-of-tags'] = db.tags.count()
    stats['number-of-agents'] = db.agents.count()
    stats['number-of-filters'] = db.filters.count()
    stats['number-of-unfiltered-articles'] = db.articles.find({'show' : True}).count()
    stats['number-of-filtered-articles'] = stats['number-of-articles'] - stats['number-of-unfiltered-articles']
    stats['number-of-unread-articles'] = db.articles.find({'show' : True, 'read' : False}).count()
    stats['number-of-marked-articles'] = db.articles.find({'show' : True, 'marked' : True}).count()

    stats['database-size'] = db.command("dbstats")['dataSize'] / 1024.0**2
    stats['last-update'] = db.feeds.find(sort = [('last-update', -1)], limit = 1)[0]['last-update']

    return render_template('./statistics.html', stats = stats, feeds = g.feeds)

if __name__ == '__main__':

    app.run(debug = True)
