#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from flask import Flask
from flask import g, render_template, jsonify

from celery import Celery

from base import init as dbinit

app = Flask(__name__)

# Celery configuration
# app.config['CELERY_BROKER_URL'] = 'mongodb://localhost:27017/celery'
# app.config['CELERY_RESULT_BACKEND'] = 'mongodb'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379'

celery = Celery(app.import_name, backend = app.config['CELERY_RESULT_BACKEND'], broker = app.config['CELERY_BROKER_URL'])

@app.before_request
def init():

    g.db = db = dbinit()
    g.feeds = list(db.feeds.find())
    g.tags = list(db.tags.find())
    g.agents = list(db.agents.find())
    g.filters = list(db.filters.find())

@app.route('/tasks/<string:action>')
@app.route('/tasks/<string:action>/title/<string:title>')
@app.route('/tasks/<string:action>/id/<string:identifier>')
def tasks(action, title = None, identifier = None):

    from tasks import update, download, process, update_feed_metadata, update_tag_metadata

    if action in ('update', 'download', 'process', 'update_feed_metadata', 'update_tag_metadata'):
        if action in locals():
            f = locals()[action]
            if title:
                f.delay(title = title)
            elif identifier:
                f.delay(identifier = identifier)
            else:
                f.delay()
        return jsonify({'message' : 'Ok', 'status' : 202, 'mimetype' : 'application/json'})

    jsonify({'message' : 'Not implemented', 'status' : 501, 'mimetype' : 'application/json'})

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
