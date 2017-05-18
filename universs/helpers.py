#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import xml.etree.ElementTree as etree

def read_opml(filename):
    ''' Returns RSS feed title and URL from OPML export file.'''

    folder, feeds = '', []
    tree = etree.parse(filename)
    for element in tree.iter('outline'):
        if 'title' in element.attrib:
            if 'xmlUrl' in element.attrib:
                # This is a feed...
                title, url = element.attrib['title'], element.attrib['xmlUrl']
                feeds.append((title, url, folder))
            else:
                # This is a folder...
                folder = element.attrib['title']

    return feeds
