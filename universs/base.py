#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from uuid import uuid4 as uuid
from pymongo import MongoClient

from helpers import read_opml

def init(server = 'localhost'):
    ''' Establishes a connection to the database backend and returns a handle for the database. '''

    client = MongoClient(server)
    db = client.filtr
    collections = db.collection_names()

    if 'feeds' not in collections:
        subscriptions = 'data/subscriptions.xml'
        feeds = read_opml(subscriptions)
        db.feeds.insert_many([{'_id' : str(uuid()), 'title' : title, 'url' : url, 'tags' : [folder], 'description' : '', 'whitelist' : [], 'blacklist' : []} for title, url, folder in feeds])

    return db
