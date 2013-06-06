#!/usr/bin/env python
# -*- coding: utf-8; mode: python; tab-width: 4; indent-tabs-mode: nil; c-basic-offset: 4 -*- vim:fenc=utf-8:ft=python:et:sw=4:ts=4:sts=4
from datetime import datetime, timedelta
import calendar
import locale
import numpy as np

from flup.server.fcgi import WSGIServer
from cgi import escape
import urlparse
from mako.template import Template
from mako.lookup import TemplateLookup

# enable debugging (for now)
import cgitb
cgitb.enable()

for loc in ['no_NO', 'nb_NO.utf8']:
    try:
        locale.setlocale(locale.LC_ALL, loc.encode('utf-8'))
    except locale.Error:
        pass

import os, oursql, sqlite3

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
    yield tpl.render_unicode(rows=rows, log=log, count=ctot, startdate=startdate).encode('utf-8')

    #    db = oursql.connect(db='nowiki_p',
    #            host='nowiki-p.rrdb.toolserver.org',
    #            read_default_file=os.path.expanduser('~/.my.cnf'),
    #            charset=None,
    #            use_unicode=False
    #    )
    #    cur = db.cursor()
    #    html = '<h2>Analyse</h2>\n'
    #    html += '<ul class="analysis">\n'
    #    eligible = True
    #    cur.execute('SELECT user_id, user_registration, user_editcount FROM user WHERE user_name=? LIMIT 1', [uname.encode('utf-8')])
    #    user_row = cur.fetchall()
    #    if len(user_row) != 1:
    #        html += u'<li class="fail">er ikke registrert (sjekk at brukernavnet er skrevet riktig)</li>\n'
    #        eligible = False
    #    else:
    #        user_row = user_row[0]
    #        user_id = int(user_row[0])
    #        for req in event['reqs']:

    #            if req[0] == 'edits_between':
    #                cur.execute('SELECT COUNT(rev_id) FROM revision WHERE rev_user_text=? AND rev_timestamp BETWEEN ? AND ?', [uname.encode('utf-8'), req[1], req[2]])
    #                usum = int(cur.fetchone()[0])
    #                d0 = pytz.utc.localize(datetime.datetime.strptime(str(req[1]), '%Y%m%d%H%M%S')).astimezone(osl).strftime('%d. %B %Y')
    #                d1 = pytz.utc.localize(datetime.datetime.strptime(str(req[2]), '%Y%m%d%H%M%S')).astimezone(osl).strftime('%d. %B %Y')
    #                if usum >= req[3]:
    #                    html += u'<li class="ok">har gjort minst %s redigeringer i perioden fra og med %s til %s (har gjort %s redigeringer)</li>\n' % (req[3], d0, d1, usum)
    #                else:
    #                    html += u'<li class="fail">har gjort færre enn %s redigeringer i perioden fra og med %s til %s (har gjort %s redigeringer)</li>\n' % (req[3], d0, d1, usum)
    #                    eligible = False

    #            elif req[0] == 'edits_total':
    #                if user_row[2] >= req[1]:
    #                    html += u'<li class="ok">har gjort minst %d redigeringer totalt (har gjort %d redigeringer)</li>\n' % (req[1], user_row[2])
    #                else:
    #                    html += u'<li class="fail">har gjort mindre enn %d redigeringer totalt (har gjort %d redigeringer)</li>\n' % (req[1], user_row[2])
    #                    eligible = False

    #            elif req[0] == 'registration_before':
    #                d0 = pytz.utc.localize(datetime.datetime.strptime(str(req[1]), '%Y%m%d%H%M%S')).astimezone(osl).strftime('%d. %B %Y')
    #                if user_row[1] == None:
    #                    # før 2005/2006 en gang
    #                    html += u'<li class="ok">registrerte seg før %s</li>\n' % (d0) 
    #                else:
    #                    regdate = int(user_row[1])
    #                    d1 = pytz.utc.localize(datetime.datetime.strptime(str(user_row[1]), '%Y%m%d%H%M%S')).astimezone(osl).strftime('%e. %B %Y')
    #                    if regdate < req[1]:
    #                        html += u'<li class="ok">registrerte seg før %s (registrerte seg %s)</li>\n' % (d0, d1)
    #                    else:
    #                        html += u'<li class="fail">registrerte seg etter %s (registrerte seg %s)</li>\n' % (d0, d1)
    #                        eligible = False

    #            elif req[0] == 'has_not_role':
    #                cur.execute('SELECT COUNT(ug_user) FROM user_groups WHERE ug_user=? AND ug_group=?', (user_id, req[1]))
    #                usum = int(cur.fetchall()[0][0])
    #                if usum == 0:
    #                    html += u'<li class="ok">er ikke en %s</li>\n' % req[1]
    #                else:
    #                    html += u'<li class="fail">er en %s</li>\n' % req[1]
    #                    eligible = False
                
    #    html += '</ul>'
    #    html += '<h2>Resultat</h2>'

    #    if eligible:
    #        extra = '.'
    #        if 'extra_reqs' in event and len(event['extra_reqs']) > 0:
    #            extra = ', forutsett at <ul>\n'
    #            for ext in event['extra_reqs']:
    #                extra += u'<li>%s</li>\n' % ext.replace('{USER}', uname)
    #            extra += '</ul>'
    #        html += '<div id="result" class="success">%s er stemmeberettiget ved <a title="%s" href="%s">%s</a>%s</div>' % (uname, event['name'], event['url'], event['name'], extra)
    #    else:
    #        html += '<div id="result" class="fail">%s er ikke stemmeberettiget ved <a title="%s" href="%s">%s</a>. </div>' % (uname, event['name'], event['url'], event['name'])


WSGIServer(app).run()

