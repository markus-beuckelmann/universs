# Universs

`universs` is a minimalistic, self-hosted RSS reader implemented in Python, developed to bring back control over your feeds. It uses [Celery](http://www.celeryproject.org/) as an asynchronous task queue to update feeds in the background and write them to a [MongoDB](https://docs.mongodb.com/) database backend. The HTTP part of the application is handled by the excellent [Flask](https://github.com/pallets/flask) micro framework. Overall, `universs` aims to be simple, fast and to be able to cope with possibly millions of articles.

## Installation

The current release is mostly suitable for developers. Have look at the [Development](/#development) section below.

## Features

Please note that `universs` is still under development. At the moment we only support the following core features:

* Entirely self-hosted RSS reader
* Automatic feed update
* Tags/Categories
* Keyboard shortcuts

Have a look at the [feature requests](/#feature-requests) below if you want to contribute!

## Requirements

`universs` is written for Python 3. You can find all requirements in the `requirement.txt` file in this repository, and install them using `pip install -r requirements.txt`.

# Development

There are many way to get started with the development setup, feel free to adjust that to your own needs. Here is what I do:
* Create a virtual environment: `mkvirtualenv -p /usr/bin/python3 universs`
* Activate the environment: `source <PATH>/universs/bin/activate.env`
* `git clone` the repository and install `universs` using `pip install -e .`

Then to actually run the development server:
* `export FLASK_APP=universs`
* `export FLASK_DEBUG=true`
* `flask run`

Finally, you need to start at lest one [Celery](http://www.celeryproject.org/) instance to fetch the feeds automatically in the background:
* `celery -A universs.tasks worker -B --loglevel=info`

## Further Information for Developers

* The Celery backend can be configured in `universs/__init__.py`.
* You can find and modify the Celery schedule in `universs/tasks.py`. The current default is a roulette update every ten minutes and a full update once a day.

## Feature Requests

If you want to work on one of the following features, please look out for [existing issues](https://github.com/markus-beuckelmann/universs/issues) first and let other people know some details on how you plan to contribute this feature.

* Filters for articles
* [i18n](https://en.wikipedia.org/wiki/Internationalization_and_localization) (currently only available in German)
* Import/Export ([OPML](https://en.wikipedia.org/wiki/OPML))
* Support for RSS output
* Save articles to [Pocket](https://getpocket.com/) / [Wallabag](https://wallabag.org/en)
* Full-text RSS (wherever necessary)
* Search feeds / articles
* Overall and per-feed statistics (including graphs)
* Improve appearance and usability on mobile devices (e.g. smartphones, tablets)
* Authentication (possibly [OAuth 2.0](https://en.wikipedia.org/wiki/OAuth))
* LaTeX support e.g. using [MathJax](https://www.mathjax.org/)

## MongoDB

* Backup: `mongodump -d universs -o mongodump/`
* Restore: `mongorestore -d universs mongodump/universs`

## License

GNU Affero General Public License (AGPL), see LICENSE.txt for further details.
