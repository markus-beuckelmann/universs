#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from app import celery
from base import init as dbinit
from rss import pull

from pymongo.errors import DuplicateKeyError

from datetime import datetime
from hashlib import md5

@celery.task(name = 'universs.update')
def update(*args, **kwargs):
    ''' Pulls RSS articles from feeds and pushes new articles to database. '''

    db = dbinit()

    # This will automatically either download one specified feed or all feeds listed in the database
    download(*args, **kwargs)

    print('%d RSS articles are waiting to be processed.' % (db.downloads.count(),))
    N = process()
    print('Updating metadata.')
    update_feed_metadata(*args, **kwargs)
    update_tag_metadata()

    # Return the number of new articles
    return N

@celery.task(name = 'universs.download')
def download(*args, **kwargs):
    ''' Pulls RSS articles from one feed and pushes new articles to database. '''

    db = dbinit()

    feeds = []
    if 'title' in kwargs:
        feed = db.feeds.find_one({'title' : kwargs['title']})
        if feed:
            feeds = [(feed['title'], feed['url'])]
    elif 'identifier' in kwargs:
        feed = db.feeds.find_one({'_id' : kwargs['identifier']})
        if feed:
            feeds = [(feed['title'], feed['url'])]
    else:
        # If no feeds are specified, get all feeds from the database
        feeds = [(feed['title'], feed['url']) for feed in db.feeds.find()]

    downloads = 0
    for feed in feeds:
        articles = pull(feed, jobs = 1)
        print('Downloaded %d RSS article(s) for feed "%s"' % (len(articles), feed[0]))

        # Put all articles in a "downloads" collection. They will be processed later on...
        if articles:
            db.downloads.insert_many(articles)

        downloads += len(articles)

    return downloads

def _process(article):

    # Rename the identifier key for the database to the MD5 hash of "<feed> - <title>"
    article['_id'] = md5(article['id'].encode('utf-8')).hexdigest()

    # Insert some important flags
    article['show'] = True
    article['read'] = False
    article['marked'] = False

    return article

@celery.task(name = 'universs.process')
def process(*args, **kwargs):
    ''' Processes all downloaded articles listed in the database. '''

    # This will process all documents in the "downloads" collection, process and push new articles to the "articles" collection and delete the document from "downloads".

    db = dbinit()

    now = datetime.utcnow()

    processed, pushed = 0, 0
    for article in db.downloads.find():
        identifier = article['_id']
        article = _process(article)

        # We do not accept publishing dates in the future
        if article['date'] > now:
            article['date'] = now

        # Update some feed specific information
        feed = db.feeds.find_one({'title' : article['feed-name']})
        feed['last-update'] = datetime.utcnow()
        article['feed-id'] = feed['_id']
        article['tags'] = feed['tags']

        # Push changes to feed to the database
        db.feeds.replace_one({'_id' : feed['_id']}, feed)
        # Delete article from downloads collection
        db.downloads.delete_one({'_id' : identifier})

        try:
            # Push new articles to the collection
            db.articles.insert_one(article)
        except DuplicateKeyError:
            pass
        else:
            pushed += 1

        processed += 1

    print('Processed %d RSS articles and pushed %d new articles to the database' % (processed, pushed))

    return pushed

@celery.task(name = 'universs.update_article_metadata')
def update_article_metadata(*args, **kwargs):

    pass

@celery.task(name = 'universs.update_feed_metadata')
def update_feed_metadata(*args, **kwargs):
    ''' Updates feed metadata '''

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
    ''' Updates tag metadata. '''

    db = dbinit()

    if 'title' in kwargs:
        tag = db.tags.find_one({'title' : kwargs['title']})
    elif 'identifier' in kwargs:
        tag = db.tags.find_one({'_id' : kwargs['identifier']})
    else:
        for tag in db.tag.find():
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
