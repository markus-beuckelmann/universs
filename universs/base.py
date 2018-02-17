#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from math import ceil
from uuid import uuid4 as uuid
from pymongo import MongoClient

from universs import DEFAULT_PAGE_LIMIT, DEFAULT_SORT, SHOW_ONLY_UNREAD
from universs.helpers import read_opml

def init(server = 'localhost'):
    ''' Establishes a connection to the database backend and returns a handle for the database. '''

    client = MongoClient(server, tz_aware = True)
    db = client.filtr
    collections = db.collection_names()

    if 'feeds' not in collections:
        subscriptions = 'data/subscriptions.xml'
        feeds = read_opml(subscriptions)
        db.feeds.insert_many([{'_id' : str(uuid()), 'title' : title, 'url' : url, 'tags' : [folder], 'description' : '', 'whitelist' : [], 'blacklist' : []} for title, url, folder in feeds])

    return db

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
