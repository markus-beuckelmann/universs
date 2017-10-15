#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import feedparser
import pytz

from socket import timeout as TimeoutError
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead as IncompleteReadError
from ssl import CertificateError

from bs4 import BeautifulSoup
from datetime import datetime
from joblib import Parallel, delayed

def _parse(content, verbose = False):
    ''' Parses individual feed responses (using the feedparser package). '''

    feed = feedparser.parse(content)
    url, title = getattr(feed['feed'], 'link', ''), getattr(feed['feed'], 'title', '')

    articles = []
    for i, entry in enumerate(feed['entries']):
        if 'title' not in entry:
            # If we don't even get the article's title, skip it
            continue
        data = {'title' : entry['title'], 'feed-name' : title, 'feed-url' : url}
        data['id'] = '%s – %s' % (title, entry['title'])
        if verbose:
            print('Parsing "%s" (%s)' % (data['id'], title))
        for key in ('link', 'author', 'authors', 'rss', 'summary', 'content', 'subtitle', 'published', 'published_parsed', 'date', 'date_parsed'):
            if key in entry:
                data[key] = entry[key]
        articles.append(data)

    # Return a list of dictionaries, where every item corresponds to one entry listed in the feed
    return articles

def _post_process(articles, title = '', verbose = False):
    ''' Runs post-processing on the extracted information. '''

    for article in articles:

        if 'content' in article and isinstance(article['content'], (list, tuple)):
            if article['content'][0]['language']:
                article['language'] = article['content'][0]['language']
            article['content'] = article['content'][0]['value']
        elif 'summary' in article:
            article['content'] = article['summary']
            del article['summary']
        else:
            article['content'] = ''

        if 'authors' in article and isinstance(article['authors'], (list, tuple)) and 'name' in article['authors'][0]:
            article['author'] = article['authors'][0]['name']

        if 'published_parsed' in article:
            try:
                article['date'] = datetime(*article['published_parsed'][:6])
            except TypeError:
                article['date'] = datetime.utcnow()
        elif 'date_parsed' in article:
            article['date'] = datetime(*article['date_parsed'][:6])
        else:
            # If we can't find any information about the publishing date, let's take the time of crawling
            article['date'] = datetime.utcnow()

        if 'title' in article and 'subtitle' in article and article['title'] == article['subtitle']:
            article['subtitle'] = ''

        # Try to extract get a text-only representation of the content
        article['text'] = BeautifulSoup(article['content'], 'lxml').get_text()

        # Make sure that the following keys exist...
        for key in ('content', 'language', 'author', 'date'):
            if key not in article:
                article[key] = ''
        # Make sure the following keys don't exist
        for key in ('authors', 'published', 'published_parsed', 'date_parsed', 'subtitle', 'summary'):
            if key in article:
                del article[key]

        # Remove leading and trailing whitespace
        for key in ('content', 'text', 'title'):
            article[key] = article[key].strip()

        # Make article["date"] timezone aware
        try:
            article['date'] = pytz.utc.localize(article['date'])
        except ValueError:
            # MongoClient most likely has tz_aware=True option
            pass

        # Update the feed title if a custom name was specified
        if title:
            article['feed-name'] = title

    return articles

def _process(response, title, verbose = False):
    ''' Parses the response and calls the post-processing routine on the extracted information. '''

    articles = _parse(response, verbose = verbose)
    return _post_process(articles, title, verbose = verbose)

def _pull(title, url, feedid, timeout = 3, *args, **kwargs):
    ''' Fetches, parses and processes individual RSS feed. '''

    agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.85 Safari/537.36'
    request = Request(url, data = None, headers = {'User-Agent': agent})
    try:
        response = urlopen(request, timeout = timeout)
    except (HTTPError, URLError, TimeoutError, ConnectionResetError, IncompleteReadError, CertificateError):
        return []

    if response.status == 200:
        try:
            content = response.read()
        except (ConnectionResetError, TimeoutError, IncompleteReadError):
            return []

        # Parse the HTML/XHTML content using feedparser and post-process the entries
        articles = _process(content, title)

        # Attach the feed identifier to all articles
        for article in articles:
            article['feed-id'] = feedid

        return articles
    else:
        return []

def pull(feeds, jobs = 30, timeout = 3, verbose = 5, backend = 'multiprocessing', *args, **kwargs):
    ''' Fetches, parses and processes a list of RSS feeds in parallel. '''

    # Input should be a list of (title, url) tuples or only one such tuple
    # Output will be a list of dictionaries, where every dictionary corresponds to one article

    if isinstance(feeds, (tuple, list)) and isinstance(feeds[0], (tuple, list)):
        # Note that jobs could be more than numbers of CPUs/threads due to the network IO
        if jobs > 1:
            articles = Parallel(n_jobs = jobs, verbose = verbose, backend = backend)(delayed(_pull)(title, url, feedid, timeout = timeout) for title, url, feedid, *_ in feeds)
        else:
            articles = [_pull(title, url, feedid) for title, url, feedid, *_ in feeds]

        # Merge the results
        articles = [article for feed in articles for article in feed]
    else:
        articles = _pull(title, url, feedid, timeout = timeout)

    return articles
