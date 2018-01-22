#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from time import time
from math import ceil
from datetime import datetime
from pytz import timezone
from uuid import uuid4 as uuid

from flask import Flask
from flask import g, request, redirect, url_for, render_template, jsonify

from celery import Celery

from base import init as dbinit

app = Flask(__name__)

# Celery configuration
# app.config['CELERY_BROKER_URL'] = 'mongodb://localhost:27017/celery'
# app.config['CELERY_RESULT_BACKEND'] = 'mongodb'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379'

celery = Celery(app.import_name, backend = app.config['CELERY_RESULT_BACKEND'], broker = app.config['CELERY_BROKER_URL'])

DEFAULT_PAGE_LIMIT = 100
DEFAULT_SORT = 'date'
TIMEZONE = 'Europe/Berlin'
TIMEFORMAT = '%d.%m.%Y, %H:%M:%S Uhr (%Z)'
# Set this to 'unread' to only show unread articles by default
SHOW_ONLY_UNREAD = 'unread'

def now():
    return timezone(TIMEZONE).localize(datetime.now())

@app.before_request
def init():

    g.db = db = dbinit()
    g.feeds = list(db.feeds.find())
    g.tags = list(db.tags.find())
    g.agents = list(db.agents.find())
    g.filters = list(db.filters.find())

def get(db, query):
    ''' Retrieves articles from the database backend. '''

    # Obtain a list of dictionaries containing all permitted flags
    if query.get('all', False):
        whitelist = ('show', 'marked', 'starred')
    else:
        whitelist = ('show', 'read', 'marked', 'starred')
    flags = [{key : query[key]} for key in filter(lambda x: x, query) if key in whitelist]

    match = {'$and' : []}
    if 'feed-id' in query:
        match['$and'].append(
            {'feed-id' : query['feed-id']}
        )
    if 'tags' in query:
        if isinstance(query['tags'], (list, tuple)):
            tags = list(query['tags'])
        else:
            tags = [query['tags']]
        match['$and'].append(
            {'tags' : {'$in' : tags}}
        )

    if query.get('default', False):
        conditions = [{'$and' : [{'read' : False}]}, {'$or' : [{'marked' : True}]}]
    else:
        conditions = [
            {'$and' : flags},
            # You can add additional clauses here...
            # e.g. {'$or' : [{'marked' : True, 'starred' : True}]}
            # if you want to ALWAYS show articles that are both marked and starred.
            #
            # In general: item will be in the pipeline if any of conditions on this level evaluates to True.
        ]
    # Now: Append the rest of our conditions to the query...
    match['$and'].append({'$or' : conditions})
    offset, limit = query.get('offset', 0), query.get('limit', DEFAULT_PAGE_LIMIT)
    order = 1 if 'reversed' in query else -1

    # This is an aggregation approach but currently fails for large number of articles due to memory limits.
    # Even using allowDiskUse = True does not work as a workaround here.

    # pipeline = [
    #     {'$match' : match},
    #     {'$sort' : {query.get('sort', DEFAULT_SORT) : order}},
    #     # This is needed to count the total number of matched documents
    #     {'$group' : {
    #         '_id' : None,
    #         'total' : {'$sum' : 1},
    #         'results' : {'$limit' : 500, '$push' : '$$ROOT'}
    #     }},
    #     {'$project' : {
    #         'total' : 1,
    #         'results' : {
    #             '$slice' : ['$results', offset, limit]
    #         },
    #     }},
    #     {'$addFields' : {
    #         'size' : {'$size' : '$results'},
    #         'pages' : {'$ceil' : {'$divide' : ['$total', limit]}},
    #         # Also add everything from the query dictionary in the response
    #         **{k : v for k, v in query.items()}
    #     }},
    # ]
    # # Finally: Query the database...
    # args, kwargs = [], {'allowDiskUse' : True}
    # cursor = db.articles.aggregate(pipeline, *args, **kwargs)
    # response = list(cursor)

    pipeline = [
        {'$match' : match},
        {'$sort' : {query.get('sort', DEFAULT_SORT) : order}},
        # Write a temporary "output" collection
        {'$out' : 'output'}
    ]
    # Finally: Query the database...
    args, kwargs = [], {'allowDiskUse' : True}
    # First query will perform, matching, sorting and writing to a temporary collection
    cursor1 = db.articles.aggregate(pipeline, *args, **kwargs)
    # Second query will simply read from the temporary collection
    cursor2 = db.output.find(skip = offset, limit = limit)

    # Build the repsonse
    response = {k : v for k, v in query.items()}
    response['total'] = db.output.count()
    response['pages'] = ceil(response['total'] / limit)
    response['results'] = list(cursor2)
    response['size'] = len(response['results'])

    # Delete the temporary collection
    db.output.drop()

    return response

def build_query(request, query = {}):
    ''' Builds the query dictionary object to specify the database query. '''

    # Only show articles with "show = True"
    query.update({'show' : True})

    # Pagination
    page = request.args.get('page', 1)
    limit = int(request.args.get('limit', DEFAULT_PAGE_LIMIT))
    offset = max(0, (int(page) - 1) * limit)
    query.update({'limit' : limit, 'offset' : offset})
    # Sorting
    query.update({'sort' : request.args.get('sort', DEFAULT_SORT)})
    if 'reversed' in request.args:
        query.update({'reversed' : True})

    # Default behavior
    if SHOW_ONLY_UNREAD == 'unread':
        query['read'] = False

    if 'read' in request.args:
        query['read'] = True
    elif 'unread' in request.args:
        query['read'] = False
    elif 'all' in request.args:
        query['all'] = True
    else:
        query['default'] = True
    if 'marked' in request.args:
        query['marked'] = True
    elif 'unmarked' in request.args:
        query['marked'] = False
    if 'starred' in request.args:
        query['starred'] = True
    elif 'unstarred' in request.args:
        query['starred'] = False

    return query

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

@app.route('/')
@app.route('/feeds')
@app.route('/feeds/<string:action>', methods = ['GET', 'POST'])
@app.route('/feeds/<string:action>/<path:title>', methods = ['GET', 'POST'])
def feeds(action = None, title = None):

    db = g.db

    if request.method == 'POST':
        if action == 'new':
            feed = {'_id' : str(uuid()), 'title' : request.form['title'], 'url' : request.form['url'], 'description' : request.form['description'], 'whitelist' : [], 'blacklist' : [], 'active' : True}
            for key in ('total-articles', 'marked-articles', 'visible-articles', 'unread-articles'):
                feed[key] = 0
            feed['tags'] = list(filter(bool, map(lambda tag: tag.strip(), request.form['tags'].split(','))))

            # Push new feed to the database
            db.feeds.insert_one(feed)

            from tasks import update
            # Pull, process and push articles from new feed
            update.delay(identifier = feed['_id'])

        return redirect(url_for('feeds'))
    else:
        if action == 'new':
            return render_template('./feeds/new.html', feeds = g.feeds, agents = g.agents, filters = g.filters, now = now())
        elif action == 'delete':
            if title:
                feed = db.feeds.find_one({'title' : title})
                # Delete all articles that belong to the feed
                db.articles.delete_many({'feed-id' : feed['_id']})
                # Delete the feed
                db.feeds.delete_one({'_id' : feed['_id']})
            return redirect(url_for('feeds'))
        elif action == 'deactivate':
            if title:
                feed = db.feeds.find_one({'title' : title})
                if feed and feed['active']:
                    feed['active'] = False
                    db.feeds.replace_one({'_id' : feed['_id']}, feed)
            return redirect(url_for('feeds'))
        elif action == 'activate':
            if title:
                feed = db.feeds.find_one({'title' : title})
                if feed and not feed['active']:
                    feed['active'] = True
                    db.feeds.replace_one({'_id' : feed['_id']}, feed)
            return redirect(url_for('feeds'))
        else:
            if title:
                feed = db.feeds.find_one({'title' : title})
                if feed:
                    query = build_query(request, {'feed-id' : feed['_id']})
                    response = get(db, query)
                else:
                    response = {}
                return render_template('./feeds/feeds.html', name = title, feeds = g.feeds, feed = feed, response = response, now = now())
            else:
                query = build_query(request)
                response = get(db, query)
                return render_template('./feeds/feeds.html', name = title, feeds = g.feeds, feed = {'title' : 'Alle Artikel'}, response = response, special = True, now = now())

@app.route('/tags')
@app.route('/tags/<string:title>')
def tags(title = None):

    db = g.db

    if title:
        tag = db.tags.find_one({'title' : title})
        if tag:
            query = build_query(request, {'tags' : tag['title']})
            response = get(db, query)
        else:
            response = {}
        return render_template('tags/tags.html', name = title, tag = tag, tags = g.tags, response = response, now = now())
    else:
        return render_template('tags/tags.html', name = title, tags = g.tags, response = {}, now = now())

@app.route('/settings')
@app.route('/settings/feed/<string:name>', methods = ['GET', 'POST'])
def settings(name = None):

    db = g.db

    # Edit the settings...
    if request.method == 'POST':
        f = {'title' : request.form['title'], 'url' : request.form['url'], 'description' : request.form['description'], 'whitelist' : [], 'blacklist' : []}
        f['tags'] = list(filter(bool, map(lambda tag: tag.strip(), request.form['tags'].split(','))))
        feed = db.feeds.find_one({'title' : name})
        for key in filter(lambda key: key.startswith('agents-') or key.startswith('filters-'), request.form.keys()):
            element, i = key.split('-')
            value = request.form[key]
            if value:
                f[element].append(value)

        # Save a copy of all tags before the modification
        tags_before = set(feed['tags'])

        # If the title changed, we need to update the "feed-name" field in affected articles
        if feed['title'] != f['title']:
            db.articles.update_many({'feed-id' : feed['_id']}, {'$set' : {'feed-name' : f['title']}})

        # Update the feed information in the database
        feed.update(f)
        db.feeds.replace_one({'_id' : request.form['id']}, feed)

        # This will create a list of all tags that were removed in the update procedure
        deleted_tags = list(tags_before - set(f['tags']))
        if deleted_tags:
            # Remove the deleted tags from the respective articles
            db.articles.update_many({'feed-id' : feed['_id']}, {'$pop' : {'tags': {'$each' : deleted_tags}}})

        # This will create a list of all tags that haven't been assigned before
        new_tags = list(set(f['tags']) - tags_before)
        if new_tags:
            # Append the new tags to the respective articles
            db.articles.update_many({'feed-id' : feed['_id']}, {'$push' : {'tags': {'$each' : new_tags}}})

        from tasks import update_feed_metadata, update_tag_metadata

        # Update the metadata in the feed
        update_feed_metadata.delay(identifier = feed['_id'])
        # Update metadata for affected tags
        [update_tag_metadata.delay(title = title) for title in deleted_tags + new_tags]

        return redirect(url_for('settings'))
    # Show settings
    else:
        if name:
            feed = db.feeds.find_one({'title' : name})
            return render_template('feeds/settings.html', name = name, feed = feed, feeds = g.feeds, agents = g.agents, filters = g.filters)
        return render_template('./settings.html', feeds = g.feeds)

@app.route('/filters')
@app.route('/filters/<string:action>', methods = ['GET', 'POST'])
@app.route('/filters/<string:action>/<string:uid>', methods = ['GET', 'POST'])
def filters(action = None, uid = None):

    db = g.db

    if action == 'new':
        if request.method == 'POST':
            f = {'_id' : request.form['id'], 'name' : request.form['name'], 'description' : request.form['description'], 'blocks' : []}
            for key in filter(lambda key: key.startswith('block-'), request.form.keys()):
                block, i, j = key.split('-')
                i, j = int(i), int(j)
                value = request.form[key]
                if len(f['blocks']) > i:
                    f['blocks'][i].append(value)
                else:
                    f['blocks'].append([value])
            db.filters.insert_one(f)
            return redirect(url_for('filters'))
        else:
            uid = int(time())
            return render_template('./filters/filter-new.html', agents = g.agents, feeds = g.feeds, uid = uid)
    elif action == 'edit':
        if request.method == 'POST':
            f = {'id' : request.form['id'], 'name' : request.form['name'], 'description' : request.form['description']}
            #@TODO: Here is some code missing to take changes to blocks into account
            x = db.filters.find_one({'_id' : request.form['id']})
            x.update(f)
            db.filters.replace_one({'_id' : request.form['id']}, x)
        else:
            f = db.filters.find_one({'_id' : uid})
            return render_template('./filters/filter-edit.html', f = f, feeds = g.feeds)
        return redirect(url_for('filters'))
    elif action == 'delete':
        db.filters.delete_one({'_id' : uid})
        return redirect(url_for('filters'))
    return render_template('./filters/filters.html', filters = g.filters, feeds = g.feeds)

@app.route('/agents')
@app.route('/agents/<string:action>', methods = ['GET', 'POST'])
@app.route('/agents/<string:action>/<string:uid>', methods = ['GET', 'POST'])
def agents(action = None, uid = None, name = None):

    db = g.db

    if action == 'new':
        if request.method == 'POST':
            a = {'_id' : request.form['id'], 'name' : request.form['name'], 'description' : request.form['description'], 'language' : request.form['language'], 'code' : request.form['code']}
            db.agents.insert_one(a)
            return redirect(url_for('agents'))
        else:
            uid = int(time())
            return render_template('./agents/agent-new.html', uid = uid, feeds = g.feeds)
    elif action == 'edit':
        if request.method == 'POST':
            a = {'name' : request.form['name'], 'description' : request.form['description'], 'language' : request.form['language'], 'code' : request.form['code'], }
            x = db.agents.find_one({'_id' : request.form['id']})
            x.update(a)
            db.agents.replace_one({'_id' : request.form['id']}, x)
        else:
            a = db.agents.find_one({'_id' : uid})
            return render_template('./agents/agent-edit.html', a = a, feeds = g.feeds)
        return redirect(url_for('agents'))
    elif action == 'delete':
        db.agents.delete_one({'_id' : uid})
        return redirect(url_for('agents'))
    else:
        agents = g.get('agents', [])
        return render_template('./agents/agents.html', feeds = g.feeds, agents = agents)

@app.route('/flag/<string:f>/<string:uid>')
def flag(f, uid):

    db = g.db

    article = db.articles.find_one({'_id' : uid})
    if article:
        if f == 'read' and not article['read']:
            article['read'] = True
            # Update feed and tag metadata
            db.feeds.update_one({'_id' : article['feed-id']}, {'$inc' : {'unread-articles' : -1}})
            db.tags.update_many({'title' : {'$in' : article['tags']}}, {'$inc' : {'unread-articles' : -1}})
        elif f == 'unread' and article['read']:
            article['read'] = False
            # Update feed and tag metadata
            db.feeds.update_one({'_id' : article['feed-id']}, {'$inc' : {'unread-articles' : 1}})
            db.tags.update_many({'title' : {'$in' : article['tags']}}, {'$inc' : {'unread-articles' : 1}})
        elif f in ('mark', 'marked') and not article['marked']:
            article['marked'] = True
        elif f in ('unmark', 'unmarked') and article['marked']:
            article['marked'] = False
        elif f in ('star', 'starred') and not article['starred']:
            article['starred'] = True
        elif f in ('unstar', 'unstarred') and article['starred']:
            article['starred'] = False
        else:
            return jsonify({'message' : 'No action required', 'status' : 200, 'mimetype' : 'application/json'})

        # Push changes to database
        db.articles.replace_one({'_id' : article['_id']}, article)
        return jsonify({'message' : 'Ok', 'status' : 200, 'mimetype' : 'application/json'})
    else:
        return jsonify({'message' : 'Article not found', 'status' : 200, 'mimetype' : 'application/json'})

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
    stats['number-of-inactive-feeds'] = db.feeds.find({'active' : False}).count()
    stats['number-of-articles'] = db.articles.count()
    stats['number-of-tags'] = db.tags.count()
    stats['number-of-agents'] = db.agents.count()
    stats['number-of-filters'] = db.filters.count()
    stats['number-of-unfiltered-articles'] = db.articles.find({'show' : True}).count()
    stats['number-of-filtered-articles'] = stats['number-of-articles'] - stats['number-of-unfiltered-articles']
    stats['number-of-unread-articles'] = db.articles.find({'show' : True, 'read' : False}).count()
    stats['number-of-marked-articles'] = db.articles.find({'show' : True, 'marked' : True}).count()
    stats['number-of-starred-articles'] = db.articles.find({'show' : True, 'starred' : True}).count()

    stats['database-size'] = db.command("dbstats")['dataSize'] / 1024.0**2
    stats['last-update'] = db.feeds.find(sort = [('last-update', -1)], limit = 1)[0]['last-update']

    return render_template('./statistics.html', stats = stats, feeds = g.feeds)

@app.template_filter('dt')
def _jinja2_filter_dt(date):

    date = date.replace(tzinfo = timezone('UTC'))
    date = date.astimezone(timezone(TIMEZONE))
    return date.strftime(TIMEFORMAT)

if __name__ == '__main__':

    app.run(debug = True)
