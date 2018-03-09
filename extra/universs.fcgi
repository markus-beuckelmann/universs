#!/var/environments/universs/bin/python

from flup.server.fcgi import WSGIServer
from universs import app

if __name__ == '__main__':
	WSGIServer(app).run()
