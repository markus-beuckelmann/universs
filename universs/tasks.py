#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import numpy as np
import pytz

from app import celery
from base import init as dbinit
from rss import pull
from helpers import httpcheck

from pymongo.errors import DuplicateKeyError, BulkWriteError

from datetime import datetime
from hashlib import md5
from collections import Counter

# By default automatically perform a full update every hour
celery.conf.beat_schedule = {
    'auto-update': {
        'task': 'universs.update',
        'schedule': 3600.0,
    },
}
celery.conf.timezone = 'UTC'

def bulk(db, *args, **kwargs):
    ''' Returns all active feeds in the database. '''
    return [(feed['title'], feed['url'], feed['_id']) for feed in db.feeds.find({'active' : True})]

def batch(db, *args, **kwargs):
    ''' Returns a random feed sample of active feeds in the database. '''

    # Choose a batch size (size of the sample)
    k = 50
    cursor = db.feeds.aggregate([{'$match' : {'active' : True}}, {'$sample' : {'size' : k}}])
    return [(feed['title'], feed['url'], feed['_id']) for feed in cursor]

def roulette(db, *args, **kwargs):
    ''' Returns a random feed sample following the roulette wheel selection scheme. '''

    # Define a scoring function
    scoring = lambda feed: np.log10(max(feed['total-articles'], 10))
    feeds = list(db.feeds.find({'active' : True}))
    G = sum(map(scoring, feeds))
    # Map to probabilities (i.e normalization)
    probabilities = lambda feed: scoring(feed) / G

    # Choose a batch size (size of the sample)
    k = 50
    sample = np.random.choice(feeds, size = k, p = list(map(probabilities, feeds)))
    return [(feed['title'], feed['url'], feed['_id']) for feed in sample]

@celery.task(name = 'universs.update')
def update(*args, **kwargs):
    ''' Pulls RSS articles from feeds and pushes new articles to database and updates metadata. '''

    methods = ('bulk', 'batch', 'roulette')
    if 'method' not in kwargs or kwargs['method'] not in methods:
        method = 'bulk'
    else:
        method = kwargs['method']

    db = dbinit()
    now = pytz.utc.localize(datetime.utcnow())

    # Test internet connectivity
    if not httpcheck():
        print('No internet connectivity. Aborting.')
        return False

    feeds = []
    if 'title' in kwargs:
        feed = db.feeds.find_one({'title' : kwargs['title']})
        if feed:
            feeds = [(feed['title'], feed['url'], feed['_id'])]
    elif 'identifier' in kwargs:
        feed = db.feeds.find_one({'_id' : kwargs['identifier']})
        if feed:
            feeds = [(feed['title'], feed['url'], feed['_id'])]
    else:
        if method == 'bulk':
            # Update all active feeds
            feeds = bulk(db, *args, **kwargs)
        elif method == 'batch':
            # Draw a random feed sample
            feeds = batch(db, *args, **kwargs)
        elif method == 'roulette':
            # Roulette wheel selection
            feeds = roulette(db, *args, **kwargs)

    print('Update method: %s • %s: %d' % (method, 'Batch size' if method in ('batch', 'roulette') else 'Feeds', len(feeds)))

    # This will download the respective feeds and put new articles in the "downloads" collection
    download(feeds, *args, **kwargs)

    print('Updating feed and tag metadata.')

    # Update "last-update" timestamp in feed information
    for title, url, feedid in feeds:
        feed = db.feeds.find_one({'_id' : feedid})
        feed['last-update'] = now
        db.feeds.replace_one({'_id' : feedid}, feed)

    # Find out how many new articles exist per feed
    feed_counter = Counter(element['feed-id'] for element in db.downloads.find(projection = ('feed-id',)))
    tag_counter = Counter()

    # Now update the respective feed metadata (e.g. total number of articles, etc.)
    for feedid in feed_counter:
        feed = db.feeds.find_one({'_id' : feedid})
        if feed:
            for key in ('total-articles', 'visible-articles', 'unread-articles'):
                feed[key] += feed_counter[feedid]
            db.feeds.replace_one({'_id' : feedid}, feed)

            # Update the tag counter
            tag_counter += Counter(feed['tags'] * feed_counter[feedid])

    # Update the respective tag metadata
    for title in tag_counter:
        tag = db.tags.find_one({'title' : title})
        if tag:
            for key in ('total-articles', 'visible-articles', 'unread-articles'):
                tag[key] += tag_counter[title]
            db.tags.replace_one({'_id' : tag['_id']}, tag)
        else:
            # This is a new tag
            pass

    # Finally, transfer the articles to the actual "articles" collection and wipe "downloads" collection
    N = process()
    return N

@celery.task(name = 'universs.download')
def download(feeds, *args, **kwargs):
    ''' Pulls RSS articles from one feed and pushes new articles to database. '''

    db = dbinit()

    # Use 120 threads, hide joblib output and set a 3s timeout for urlopen()
    jobs, verbose, timeout = 120, 0, 3

    # Note: If you are using Celery for asynchronous tasks, you have to use the 'threading' backend instead of 'multiprocessing'
    articles = pull(feeds, jobs, timeout = timeout, verbose = verbose, backend = 'threading')
    queue = []

    for article in articles:
        # Now check if the article is already in db.articles (i.e. is an already processed, old article)
        uid = '%s - %s' % (article['feed-id'], article['title'])
        uid = md5(uid.encode('utf-8')).hexdigest()

        # Note that .find(...).limit(1).count() is for some reason faster than .find_one()
        if db.articles.find({'_id' : uid}).limit(1).count():
            continue
        else:
            # Assign the correct ID
            article['_id'] = uid

            # If it's not in db.downloads, we'll add it to the queue
            if not db.downloads.find({'_id' : uid}).limit(1).count():
                queue.append(article)

    if queue:
        # Put all articles in a "downloads" collection. They will be processed later on...
        if len(queue) > 1:
            try:
                db.downloads.insert_many(queue, ordered = False)
            except BulkWriteError:
                pass
        else:
            db.downloads.insert_one(queue[0])

    # Print a status message
    print('%d downloaded, %d queued articles.' % (len(articles), len(queue)))

    return len(articles)

@celery.task(name = 'universs.process')
def process(*args, **kwargs):
    ''' Processes all downloaded articles listed in the database. '''

    # This will process all documents in the "downloads" collection, process and push new articles to the "articles" collection and delete the document from "downloads".

    db = dbinit()
    now = pytz.utc.localize(datetime.utcnow())

    processed, pushed = 0, 0
    for article in db.downloads.find():

        # First of all, assert that the article's ID is correct, i.e. the MD5 hash of "<feed-id> - <title>"
        uid = md5(('%s - %s' % (article['feed-id'], article['title'])).encode('utf-8')).hexdigest()
        #assert article['_id'] == uid

        # Insert some important flags
        article['show'] = True
        article['read'] = False
        article['marked'] = False
        article['starred'] = False

        # We do not accept publishing dates in the future
        if article['date'] > now:
            article['date'] = now

        # Store the time the article was downloaded
        article['downloaded'] = now

        # Get some feed specific information from the database
        feed = db.feeds.find_one({'title' : article['feed-name']})
        article['tags'] = feed['tags']

        # Delete article from downloads collection
        db.downloads.delete_one({'_id' : uid})

        try:
            # Push new articles to the collection
            db.articles.insert_one(article)
        except DuplicateKeyError:
            pass
        else:
            pushed += 1

        processed += 1

    print('%d articles processed, %d new articles pushed to the database' % (processed, pushed))

    return pushed

@celery.task(name = 'universs.update_article_metadata')
def update_article_metadata(*args, **kwargs):
    pass

@celery.task(name = 'universs.update_feed_metadata')
def update_feed_metadata(*args, **kwargs):
    ''' Performs a full update on a feed's metadata. '''

    db = dbinit()

    if 'title' in kwargs:
        feed = db.feeds.find_one({'title' : kwargs['title']})
    elif 'identifier' in kwargs:
        feed = db.feeds.find_one({'_id' : kwargs['identifier']})
    else:
        for feed in db.feeds.find():
            update_feed_metadata(identifier = feed['_id'])
        return True

    if feed:

        # Total number of articles (including filtered/hidden)
        feed['total-articles'] = db.articles.find({'feed-id' : feed['_id']}).count()
        # Number of articles that are visible
        feed['visible-articles'] = db.articles.find({'feed-id' : feed['_id'], 'show' : True}).count()
        # Number of unread articles
        feed['unread-articles'] = db.articles.find({'feed-id' : feed['_id'], 'show' : True, 'read' : False}).count()
        # Number of marked articles
        feed['marked-articles'] = db.articles.find({'feed-id' : feed['_id'], 'show' : True, 'marked' : True}).count()
        # Number of starred articles
        feed['starred-articles'] = db.articles.find({'feed-id' : feed['_id'], 'show' : True, 'starred' : True}).count()

        # If any filters are registered, apply them to fill up feed["articles"]
        # if len(feed['filters']) > 0:
        #     masks = []
        #     for filterid in feed['filters']:
        #         f = db.filters.find_one({'_id' : filterid})
        #         if f and 'def filter(' in f['code']:
        #             # Compile the filter code into _filter() function in locals
        #             exec(f['code'].replace('def filter(', 'def _filter('))
        #             # Run _filter() on respective articles
        #             masks.append(list(map(locals()['_filter'], articles)))

        #         # Transpose the boolean masks and compute row-wise logical and
        #         mask = list(map(lambda x: all(x), zip(*masks)))
        #         indices = [i for i, element in enumerate(mask) if element]
        #         feed["articles"] = [articles[i]['_id'] for i in indices]
        # else:
        #     feed["articles"] = [article['_id'] for article in articles]

        # Push changes to the database
        db.feeds.replace_one({'_id' : feed['_id']}, feed)

    return True

@celery.task(name = 'universs.update_tag_metadata')
def update_tag_metadata(*args, **kwargs):
    ''' Performs a full update on a tag's metadata. '''

    db = dbinit()

    if 'title' in kwargs:
        tag = db.tags.find_one({'title' : kwargs['title']})
    elif 'identifier' in kwargs:
        tag = db.tags.find_one({'_id' : kwargs['identifier']})
    else:
        for tag in db.tags.find():
            update_tag_metadata(identifier = tag['_id'])
        return True

    if tag:

        # Build a list of feed IDs that have the respective tag assigned
        tag['feeds'] = [feed['_id'] for feed in db.feeds.find({'tags' : {'$in' : [tag['title']]}})]

        # If there are no feeds assigned, then we can delete the tag
        if len(tag['feeds']) == 0:
            db.tags.delete_one({'_id' : tag['_id']})
            return True

        # Total number of articles (including filtered/hidden)
        tag['total-articles'] = db.articles.find({'tags' : {'$in' : [tag['title']]}}).count()
        # Number of articles that are visible
        tag['visible-articles'] = db.articles.find({'show' : True, 'tags' : {'$in' : [tag['title']]}}).count()
        # Number of unread articles
        tag['unread-articles'] = db.articles.find({'show' : True, 'read' : False, 'tags' : {'$in' : [tag['title']]}}).count()
        # Number of marked articles
        tag['marked-articles'] = db.articles.find({'show' : True, 'marked' : True, 'tags' : {'$in' : [tag['title']]}}).count()
        # Number of starred articles
        tag['starred-articles'] = db.articles.find({'show' : True, 'starred' : True, 'tags' : {'$in' : [tag['title']]}}).count()

        # Push the changes to the database
        db.tags.replace_one({'_id' : tag['_id']}, tag)

    else:

        # This looks like a new tag...
        if 'title' in kwargs:
            tag = {'title' : kwargs['title']}

            # Let's check if there are any feeds that use this tag
            tag['feeds'] = [feed['_id'] for feed in db.feeds.find({'tags' : {'$in' : [tag['title']]}})]
            if len(tag['feeds']) > 0:
                # Add the new tag to the database and update its metadata
                db.tags.insert_one(tag)
                return update_tag_metadata(title = tag['title'])

    return True
