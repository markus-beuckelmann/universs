#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import feedparser

from socket import timeout as TimeoutError
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup
from datetime import datetime
from joblib import Parallel, delayed

def _parse(content, verbose = False):
    ''' Parses individual feed responses (using the feedparser package). '''

    feed = feedparser.parse(content)
    url, title = getattr(feed['feed'], 'link', ''), getattr(feed['feed'], 'title', '')

    articles = []
    for i, entry in enumerate(feed['entries']):
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
        elif article['summary']:
            article['content'] = article['summary']
            del article['summary']
        else:
            article['content'] = ''

        if 'authors' in article and isinstance(article['authors'], (list, tuple)) and 'name' in article['authors'][0]:
            article['author'] = article['authors'][0]['name']

        if 'published_parsed' in article:
            article['date'] = datetime(*article['published_parsed'][:6])
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
        for key in ('authors', 'published_parsed', 'date_parsed'):
            if key in article:
                del article[key]

        # Update the feed title if a custom name was specified
        if title:
            article['feed-name'] = title

    return articles

def _process(response, title, verbose = False):
    ''' Parses the response and calls the post-processing routine on the extracted information. '''

    articles = _parse(response, verbose = verbose)
    return _post_process(articles, title, verbose = verbose)

def _pull(title, url, timeout = 3, *args, **kwargs):
    ''' Fetches, parses and processes individual RSS feed. '''

    try:
        agent = 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; FSL 7.0.6.01001)'
        request = Request(url, data = None, headers = {'User-Agent': agent})
        response = urlopen(request, timeout = timeout)
    except (HTTPError, URLError, TimeoutError, ConnectionResetError):
        return []

    if response.status == 200:
        content = response.read()
        return _process(content, title)
    else:
        return []

def pull(feeds, jobs = 30, timeout = 3, verbose = 5, *args, **kwargs):
    ''' Fetches, parses and processes a list of RSS feeds in parallel. '''

    # Input should be a list of (title, url) tuples or only one such tuple
    # Output will be a list of dictionaries, where every dictionary corresponds to one article

    if isinstance(feeds, (tuple, list)) and isinstance(feeds[0], (tuple, list)):
        # Note that jobs could be more than numbers of CPUs/threads due to the network IO
        if jobs > 1:
            articles = Parallel(n_jobs = jobs, verbose = verbose)(delayed(_pull)(title, url, timeout = timeout) for title, url in feeds)
        else:
            articles = [_pull(title, url) for title, url in feeds]

        # Merge the results
        articles = [element for article in articles for element in article]
    else:
        articles = _pull(*feeds)

    return articles
