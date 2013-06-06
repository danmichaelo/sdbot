#!/usr/bin/python

import cgitb
cgitb.enable()

import sys
sys.path.insert(0, '/data/project/sdbot/env-py2.7/lib/python2.7/site-packages/')

from werkzeug.wrappers import Response
from werkzeug.routing import Map, Rule, NotFound, RequestRedirect
from werkzeug.utils import redirect
from wsgiref.handlers import CGIHandler

from datetime import datetime, timedelta
import calendar
import locale
import numpy as np

from cgi import escape
import urlparse
from mako.template import Template
from mako.lookup import TemplateLookup

#import sys
#sys.path.insert(0, '/data/project/sdbot/env-py2.7/lib/python2.7/site-packages/')

from wsgiref.handlers import CGIHandler

import os, oursql, sqlite3


for loc in ['no_NO', 'nb_NO.utf8']:
    try:
        locale.setlocale(locale.LC_ALL, loc.encode('utf-8'))
    except locale.Error:
        pass

def fromdatetime(d):
    return d.strftime("%F %T")

def todatetime(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')

def makelink(article):
    return '//no.wikipedia.org/wiki/Wikipedia:Sletting/' + article

def app(environ, start_response):
    
    start_response('200 OK', [('Content-Type', 'text/html')])
    sql = sqlite3.connect('../../sdbot/sdbot.db')
    cur = sql.cursor()
    mindate, maxdate = map(todatetime, cur.execute('SELECT MIN(close_date), MAX(close_date) FROM closed_requests').fetchone())
    #maxdate.year*12+maxdate.month - (mindate.year*12+mindate.month)
    cm = mindate.month
    cy = mindate.year
    
    rows = []
    while cy*12+cm <= maxdate.year*12+maxdate.month:
        lastday = calendar.monthrange(cy, cm)[1]
        sd = datetime(cy, cm, 1)
        ed = datetime(cy, cm, lastday)
        cc = cur.execute('SELECT COUNT(*) FROM closed_requests WHERE close_date BETWEEN ? AND ?', [sd, ed]).fetchone()[0]
        co = cur.execute('SELECT COUNT(*) FROM closed_requests WHERE open_date BETWEEN ? AND ?', [sd, ed]).fetchone()[0]
        beholdt = 0
        slettet = 0
        for r in cur.execute('SELECT decision, COUNT(*) FROM closed_requests WHERE close_date BETWEEN ? AND ? GROUP BY decision', [sd, ed]):
            if r[0] in ['b','f','y']:
                beholdt += r[1]
            else:
                slettet += r[1]
        days = np.zeros(cc, dtype=np.int)
        if cc > 3:
            reqs = []
            i = 0
            for row in cur.execute('SELECT open_date, close_date, name FROM closed_requests WHERE close_date BETWEEN ? AND ?', [sd, ed]):
                days[i] = (todatetime(row[1]) - todatetime(row[0])).days
                reqs.append(row[2])
                i += 1
            r = ['%02d' % cm, cy, co, cc, beholdt, slettet, np.median(days)]
            dayindex = np.argsort(days)
            r.extend([days[dayindex[-1]], makelink(reqs[dayindex[-1]])])
            r.extend([days[dayindex[-2]], makelink(reqs[dayindex[-2]])])
            r.extend([days[dayindex[-3]], makelink(reqs[dayindex[-3]])])

            rows.append(r)
            #days[maxt], makelink(reqs[maxt])])
        cm += 1
        if cm > 12:
            cm = 1
            cy += 1
    
    ctot = cur.execute('SELECT COUNT(*) FROM closed_requests').fetchone()[0]
    startdate = mindate.strftime('%Y-%m-%d')
    
    
    f = open('last.log', 'r')
    log = f.read().decode('utf-8')
    f.close()
    
    mylookup = TemplateLookup(directories=['.'], input_encoding='utf-8', output_encoding='utf-8')
    tpl = Template(filename='template.html', input_encoding='utf-8', output_encoding='utf-8', lookup=mylookup)
    return tpl.render_unicode(rows=rows, log=log, count=ctot, startdate=startdate).encode('utf-8')



CGIHandler().run(app)
