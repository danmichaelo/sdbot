#!/data/project/ukbot/ENV/bin/python
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from flup.server.fcgi import WSGIServer
from .webinterface import app 

import logging
import logging.handlers


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

logger.info('Flask server started')

fh = logging.FileHandler('main.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
app.logger.addHandler(fh)

#app.debug = True  # reload on each code change

if __name__ == '__main__':
    WSGIServer(app).run()

