#encoding=utf-
# python version 2.6.6, logging version 0.5.0.5 at nightshade
# python version 2.7.1, logging version 0.5.1.2 at willow
from __future__ import unicode_literals
from wp_private import sdbotlogin, mailfrom, mailto

import sys, os
import logging
import logging.handlers
import argparse

import mwclient
import re
import locale
# except locale.Error:

import sqlite3

from danmicholoparser import DanmicholoParser

"""
CREATE TABLE deletion_request_list (id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INT, month INT, day INT, archived BOOL);
CREATE TABLE notifications (id INTEGER PRIMARY KEY AUTOINCREMENT,
    deletion_request TEXT);
"""

from datetime import datetime
runstart = datetime.now()

os.chdir(os.path.abspath(os.path.dirname(__file__)))

import platform
pv = platform.python_version()
f = open('sdbot.log','a')
f.write('python v. %s, logging v. %s\n' % (pv, logging.__version__))
f.close()

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

#smtp_handler = logging.handlers.SMTPHandler( mailhost = ('localhost', 25),
#                fromaddr = mailfrom, toaddrs = mailto, 
#                subject=u"[toolserver] SDBot crashed!")
                
#smtp_handler.setLevel(logging.ERROR)
#logger.addHandler(smtp_handler)


def total_seconds(td):
    # for backwards compability. td is a timedelta object
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6


site = mwclient.Site('no.wikipedia.org')
site.login(*sdbotlogin)
admins = [i['name'] for i in site.allusers(group = 'sysop')]

class DeletionRequest(object):
    
    @staticmethod
    def normalize_title(title):
        title = title.strip(' \t\r\n_').replace('_', ' ')
        while title.count('  '):
            title = title.replace('  ', ' ')
        return title[0].upper() + title[1:]

    r_h3_heading = re.compile(ur'^\s*\=\=\=\s*(.*?)\s*\=\=\=\s*$', re.MULTILINE)
    r_link = re.compile(ur'\[\[[: ]*(.*?)\s*\]\]')
    def __init__(self, titles, page, simulate = False):
        
        self.archival_threshold = 86400*2
        self.simulate = simulate

        self.titles = titles

        name = page.name
        self.today = datetime.utcnow()
        self.archive = False
        self.moved_to = ''
        self.status = ''

        # Deletion request does not exist
        if not page.exists: 
            logger.warning('!! Nominasjonssiden %s eksisterer ikke' % (page.name))
            return

        if page.redirect:
            target = page.redirects_to().name
            logger.warning('Nominasjonssiden "%s" har blitt flyttet til "%s"' % (page.name, target))
            self.moved_to = target
            return

        logger.info('<> %s' % ', '.join(self.titles))

        text = page.edit()
        # Find all headings
        headings = self.r_h3_heading.findall(text)
        # Malformed request
        if len(headings) != 1: 
            logger.warning('!! %s: Forventet å finne én h3-overskrift, men fant %d!' % (page.name, len(headings)))
            return

        # Find the subjects
        m_subjects = self.r_link.findall(headings[0])
        if len(m_subjects) != len(self.titles):
            logger.warning('!! %s: Forventet å finne %d lenker i overskriften, men fant %d' % (page.name, len(titles), len(m_subjects)))
            return

        self.subjects = [self.normalize_title(s) for s in m_subjects]
        
        # Wrong heading
        if not re.search(ur'(?i)^Wikipedia\:Sletting\/%s$' % re.escape(self.subjects[0]), page.name):
            logger.warning('!! %s: Den første lenken i overskriften, "%s", matcher ikke URLen"' % (page.name, self.subjects[0]))
            return

        #self.notify_uploaders(page, subject)

        # Find all decisive templates
        dp = DanmicholoParser(text)
        decisions = []
        for t_name, tpls in dp.templates.iteritems():
            if t_name in ['beholdt', 'flettet', 'flyttet', 'hurtigsletta', 'hurtigslettet', 'ny slettenominering', 'omdirigert', 'slettet', 'sletta']:
                for t in tpls:
                    decisions.append([t.begin, t_name])
        decisions.sort(key = lambda x: x[0])
        decisions = [d[1] for d in decisions]

        # Check last decision
        if len(decisions) > 0:
            logger.info('   Fant %d avgjørelse(r): %s' % (len(decisions), ', '.join(decisions)))

            if decisions[-1] == 'beholdt':
                self.status = 'b'
            elif decisions[-1] == 'flettet':
                self.status = 'f'
            elif decisions[-1] == 'flyttet':
                if len(self.subjects) != 1:
                    logger.warning('!! Vet ikke hvordan jeg skal tolke flytting når flere sider er nominert samtidig')
                    return

                self.status = 'y'
                mto = dp.templates['flyttet'][0].parameters[1]
                if not site.pages[mto].exists:
                    logger.warning('   "%s" er merket som flyttet til "%s, men siden eksisterer ikke!"', self.subjects[0], mto)
                else:
                    logger.info('   "%s" er merket som flyttet til "%s"', self.subjects[0], mto)
                    page_redir = site.Pages['Wikipedia:Sletting/%s' % mto]
                    if not page_redir.exists:
                        txt = page_redir.edit()
                        if len(txt) == 0:
                            redir_target = 'Wikipedia:Sletting/%s' % self.subjects[0]
                            logger.info('   Lager omdirigering fra "Wikipedia:Sletting/%s" til "%s"', mto, redir_target)
                            txt = '#OMDIRIGERING [[%s]]' % redir_target
                            page_redir.save(txt, summary = 'Lager omdirigering til [[%s]]' % redir_target)

                    self.subjects[0] = mto

            elif decisions[-1] == 'hurtigsletta' or decisions[-1] == 'hurtigslettet':
                self.status = 'hs'
            elif decisions[-1] == 'omdirigert':
                #if len(self.subjects) != 1:
                #    logger.warning('!! Vet ikke hvordan jeg skal tolke omdirigering når flere sider er nominert samtidig')
                #    return
                self.status = 'o'
                #mto = dp.templates['omdirigert'][0].parameters[1]
                #logger.info('"%s" er merket som omdirigert til "%s"', self.subjects[0], mto)
                #self.subjects[0] = mto
            elif decisions[-1] == 'slettet' or decisions[-1] == 'sletta':
                self.status = 's'

        # Checking for closedness
        if self.status != '': 
            self.first_rev = page.revisions(limit = 1, dir = 'newer').next()
            self.last_rev = page.revisions(limit = 1).next()
            self.open_user = self.first_rev.get('user')
            self.open_date = datetime(*self.first_rev.get('timestamp')[:6])
            self.close_user = self.last_rev.get('user')
            self.close_date = datetime(*self.last_rev.get('timestamp')[:6])

            timedelta = self.today - self.close_date
            
            # Check whether the last user was an admin
            if self.close_user not in admins and self.close_user != site.username:
                logger.warning('   %s ble avsluttet, eller redigert etter avslutning, av %s, som ikke er admin' % (page.name, self.close_user))
                if not 'sletteforslag avslutning uklar' in dp.templates:
                    self.insert_notadminwarning(page)
                #self.not_admin_closed.append((page.name, last_rev))
            elif 'sletteforslag avslutning uklar' in dp.templates:
                logger.warning('   Venter på fjerning av {{sletteforslag avslutning uklar}}')
            else:
                ts = total_seconds(timedelta)
                arkiv = 'slettet'
                if self.status in ['b','f','y']:
                    arkiv = 'beholdt'
                
                logger.info('   Avsluttet med status: %s. Arkiveres som %s om %.1f timer' % (self.status, arkiv, (self.archival_threshold-ts)/3600.))

                if self.status == 'b' or self.status == 'y':
                    firstrev = page.revisions(dir = 'newer', limit = 1).next()
                    nomdate = datetime(*firstrev['timestamp'][:6]).strftime('%Y-%m-%d')
                    for subject in self.subjects:
                        page_subject = site.Pages[subject].resolve_redirect()
                        self.insert_kept(name, page, page_subject, nomdate)
                        self.remove_template(name, page, page_subject)

                if ts >= self.archival_threshold:
                    logger.info('   Merker for arkivering')
                    self.archive = True
        #else:
            # Closing if deleted
            #page_subject = self.site.Pages[subject]
            #if not page_subject.exists:
            #    logevents = self.site.logevents(type = 'delete', title = subject)
            #    for event in logevents:
            #        if event['action'] == 'delete':
            #            timedelta = datetime.utcnow() - datetime(*event['timestamp'][:6])
            #            if (timedelta.seconds + timedelta.days * 86400) >= self.closure_threshold:
            #                self.output('Closing %s' % name)
            #                #text = '{{delh}}\n' + text
            #                text += "\n----\n{{Slettet}} av [[Bruker:%s|]]: ''%s''" % \
            #                    (event['user'], self.escape_wikilinks(event.get('comment', '').replace('{{', '<nowiki>{{</nowiki>')))
            #                try:
            #                    page.save(text, summary = 'Avslutter slettediskusjon; resultatet var slett')
            #                except mwclient.EditError, e:
            #                    self.output('Failed to close deletion request: %s' % e)
            #                return False
    
    @staticmethod
    def get_talk(page):
        talk_spaces = {
            0: 'Diskusjon',
            2: 'Brukerdiskusjon',
            4: 'Wikipedia-diskusjon',
            6: 'Fildiskusjon',
            8: 'MediaWiki-diskusjon',
            10: 'Maldiskusjon',
            12: 'Hjelpdiskusjon',
            14: 'Kategoridiskusjon',
            100: 'Portaldiskusjon'
        }
        if page.namespace == 0:
            return 'Diskusjon:' + page.name
        ns, title = page.name.split(':', 1)
        return talk_spaces[page.namespace] + ':' + title
    
    def insert_notadminwarning(self, page_nom):

        logger.info('   Setter inn {{Sletteforslag avslutning uklar}} på %s' % page_nom.name)

        template = '{{Sletteforslag avslutning uklar}}\n'

        wait_token = site.wait_token()
        while True:
            try:
                summary = 'Venter med autoarkivering pga. uklar avslutning'
                text = template + page_nom.edit()
                if self.simulate:
                    print "--------" + page_nom.name + ": " + summary + "------------"
                    print text
                else:
                    page_nom.save(text, summary = summary)
            except mwclient.EditError, e:
                try:
                    site.wait(wait_token)
                except mwclient.MaximumRetriesExceeded:
                    return logger.error('   Unable to save page!')
            else:
                return True

    def insert_kept(self, name, page_nom, page_subject, nomination_date):
        if page_subject.namespace % 2 == 0:

            talk_page = site.Pages[self.get_talk(page_subject)]
            backlinks = page_nom.backlinks(generator = False)
            if talk_page.name in backlinks:
                logger.debug('   Ikke behov for å sette inn {{Sletting-Beholdt}}')
                return

            logger.info('   Setter inn {{Sletting-beholdt}} på %s' % page_subject.name)

            kept = '{{Sletting-beholdt | %s | %s }}\n' % (nomination_date, name)

            wait_token = site.wait_token()
            while True:
                try:
                    summary = 'Beholdt etter [[%s|slettediskusjon]]' % name
                    text = kept + talk_page.edit()
                    if self.simulate:
                        print "--------" + talk_page.name + ": " + summary + "------------"
                        print text
                    else:
                        talk_page.save(text, summary = summary)
                except mwclient.EditError, e:
                    try:
                        site.wait(wait_token)
                    except mwclient.MaximumRetriesExceeded:
                        return logger.error('   Unable to save page!')
                else:
                    return True

    def remove_template(self, name, page_nom, page_subject):

        backlinks = page_nom.backlinks(generator = False, redirect = True)
        if page_subject.name in backlinks:
            logger.info('   Fjerner {{Sletting}} fra %s' % page_subject.name)

            text = page_subject.edit()
            try:
                dp = DanmicholoParser(text)
                if 'sletting' in dp.templates:
                    tpl = dp.templates['sletting'][0]
                elif 'slett' in dp.templates:
                    tpl = dp.templates['slett'][0]
                elif 'slettingfordi' in dp.templates:
                    tpl = dp.templates['slettingfordi'][0]
                else:
                    logger.info('  Fant ingen slettemal')
                    return
                text = text[0:tpl.begin] + text[tpl.end:]
                text = text.strip()
                logger.info('  vha. DanmicholoParser')
            except:
                text = re.sub(r'\{\{[Ss]lett.+?\}\}', '', text) # this may fail if template contains subtemplates
                logger.info('  vha. regexp')

            wait_token = site.wait_token()
            while True:
                try:
                    summary = 'Beholdt etter [[%s|slettediskusjon]]' % name
                    if self.simulate:
                        print "--------" + page_subject.name + ": " + summary + "------------"
                        print text
                    else:
                        page_subject.save(text, summary = summary)
                except mwclient.EditError, e:
                    try:
                        site.wait(wait_token)
                    except mwclient.MaximumRetriesExceeded:
                        return logger.error('Unable to save page')
                else:
                    return True


class SDBot(object):

    def __init__(self, simulate = False):
        self.simulate = simulate

        self.today = datetime.utcnow()

        #self.closure_threshold = 86400
        #self.notification_timeout = 86400

        self.database = sqlite3.connect('sdbot.db')
        self.cursor = self.database.cursor()

        #page = self.site.Pages['User:%s/notification-blacklist' % self.site.username]
        #text = page.edit(readonly = True)
        #self.notification_blacklist = [i.strip() for i in text.split('\n')]
        #self.notification_blacklist = []

        # Temp. fix.
        page = site.Pages['Bruker:' + site.username]
        page.get_token('edit', True)


    r_deletion_request = re.compile(ur'\{\{[Ss]letteforslag[\s]*\|(.*?)\}\}')
    r_h2_heading = re.compile(ur'^\s*\=\=\s*(.*?)\s*\=\=\s*$', re.MULTILINE)
    def read_listing(self):

        # Get members of the category:
        catname = u'Sider som er foreslått slettet'
        cat = site.categories[catname]
        catmembers = [c.name for c in cat.members() if c.namespace != 14]

        # Read listing and normalize
        page = site.Pages['Wikipedia:Sletting']
        old_text = page.edit(section = 3)
        headings = self.r_h2_heading.findall(old_text)
        if len(headings) != 1 or headings[0].lower().find('liste over slettekandidater') == -1:
            raise StandardError('Fant ikke den forventede overskriften på WP:S')

        deletion_requests = map(self.normalize_title, self.r_deletion_request.findall(re.sub('<\!--.+?-->', '', old_text)))
        deletion_requests = [[arg.strip() for arg in request.split('|')] for request in deletion_requests]
        deletion_requests = [filter(lambda x: x not in ['','hs','s','b', 'f', 'y', 'o'], request) for request in deletion_requests]

        # Compare
        flatlist = [item for sublist in deletion_requests for item in sublist]
        notlisted = list(set(catmembers).difference(set(flatlist)))
        if len(notlisted) != 0:
            logger.info('Found %d pages in %s not listed on WP:S', len(notlisted), catname)
            for pagename in notlisted:
                logger.info('  - %s', pagename)
                spage = site.pages[u'Wikipedia:Sletting/' + pagename]
                # if page.exists:
                    # logger.info('     - exists')

        # Loop over the requests
        statuses = {}
        summary = []
        archive_kept = []
        archive_deleted = []
        for n, request in enumerate(deletion_requests[:]):
            dr = DeletionRequest(titles = request, page = site.pages['Wikipedia:Sletting/' + request[0]], simulate = self.simulate)
            if dr.moved_to:
                summary.append('[[Wikipedia:Sletting/%s]] flyttet' % request[0])
                moved_to = dr.moved_to.split('/', 1)[1] # skip the Wikipedia:Sletting/ prefix
                deletion_requests[n][0] = moved_to
                statuses[moved_to] = dr.status
            else:
                statuses[request[0]] = dr.status
            if dr.archive:
                #self.output('Archiving %s as %s' % (request, archived['status']))
                deletion_requests.remove(request)
                if dr.status in ['b','f','y']:
                    archive_kept.append(dr)
                else:
                    archive_deleted.append(dr)

        monthyear = self.today.strftime('%B %Y') # e.g. "januar 2012"

        if archive_kept or archive_deleted:
            summary_arc = []
            if archive_kept:
                summary_arc.append('%d diskusjon%s til [[Wikipedia:Sletting/Beholdt/%s]]' \
                        % (len(archive_kept), 'er' if len(archive_kept) > 1 else '', monthyear))
                # Save to archive
                wait_token = site.wait_token()
                while True:
                    try:
                        self.archive_discussions('kept', archive_kept, monthyear)
                    except mwclient.InsufficientPermission:
                        raise
                    except mwclient.EditError:
                        site.wait(wait_token)
                    else:
                        break
            if archive_deleted:
                summary_arc.append('%d diskusjon%s til [[Wikipedia:Sletting/Slettet/%s]]' % \
                        (len(archive_deleted), 'er' if len(archive_deleted) > 1 else '', monthyear))
                # Save to archive
                wait_token = site.wait_token()
                while True:
                    try:
                        self.archive_discussions('deleted', archive_deleted, monthyear)
                    except mwclient.InsufficientPermission:
                        raise
                    except mwclient.EditError:
                        site.wait(wait_token)
                    else:
                        break
            summary.append('Arkiverer ' + ', '.join(summary_arc))
        if len(summary) == 0:
            summary = 'Normaliserer'
        else:
            summary = ', '.join(summary)

        # Normalize & archive

        text = '== Liste over slettekandidater (nyeste øverst) ==\n' \
            + '<!--  Legg inn nye {{sletteforslag|<navn på side>}} rett under denne linjen, øverst, ikke nederst -->'

        for request in deletion_requests:
            status = ''
            if statuses[request[0]] != '':
                status = '|' + statuses[request[0]]
            text += '\n{{Sletteforslag|%s%s}}' % ('|'.join(request), status)
        if text != old_text:
            if self.simulate:
                print "--------" + page.name + ": " + summary + "------------"
                print text
            else:
                page.save(text, summary = summary)
 
    def archive_discussions(self, archive, requests, monthyear):
        if archive == 'kept':
            page = site.Pages['Wikipedia:Sletting/Beholdt/%s' % monthyear]
            if not page.exists:
                text = '{{Arkivert|[[Wikipedia:Sletting]]}}\n{{Arkiv|{{Wikipedia:Sletting/Beholdt/Arkiv}}}}\n'
            else:
                text = page.edit()
        else:
            page = site.Pages['Wikipedia:Sletting/Slettet/%s' % monthyear]
            if not page.exists:
                text = '{{Arkivert|[[Wikipedia:Sletting]]}}\n{{Arkiv|{{Wikipedia:Sletting/Slettet/Arkiv}}}}\n'
            else:
                text = page.edit()

        # Archive
        text += '\n' + '\n'.join(('{{Sletteforslag|%s|%s}}' % ('|'.join(request.subjects), request.status) for request in requests))

        # Save
        summary = 'Arkiverer %d diskusjon%s' % (len(requests), 'er' if len(requests) > 1 else '')
        if self.simulate:
            print "--------" + page.name + ": " + summary + "------------"
            print text
        else:
            page.save(text, summary = summary)

        # Save to DB
        for request in requests:
            for subject in request.subjects:
                data = [subject, request.open_date, request.close_date, request.open_user, request.close_user, request.status, page.name]
                self.cursor.execute(u'''INSERT INTO closed_requests (name, open_date, close_date, open_user, close_user, decision, archive)
                            VALUES(?,?,?,?,?,?,?)''', data)
        if not self.simulate:
            self.database.commit()


    #def notify_uploaders(self, page, subject):
    #    self.cursor.execute("""SELECT 1 FROM notifications WHERE
    #        deletion_request = ?""", (page.name, ))
    #    if self.cursor.fetchone(): return

    #    revisions = page.revisions(dir = 'newer', limit = 1, prop = 'timestamp')
    #    timedelta = datetime.utcnow() - datetime(*revisions.next()['timestamp'][:6])

    #    if (timedelta.seconds + timedelta.days * 86400) >= self.notification_timeout:
    #        self.cursor.execute("""INSERT INTO notifications VALUES
    #            (NULL, ?)""", (page.name, ))
    #        self.database.commit()

    #        #image = self.site.Images[subject[6:]]
    #        backlinks = page.backlinks(generator = False)

    #        already_notified = [None]
    #        #imageinfo = [image.imageinfo]
    #        #imageinfo.extend(image.imagehistory())
    #        for item in imageinfo:
    #            if 'user' in item and item.get('user') not in already_notified:
    #                already_notified.append(item['user'])
    #                try:
    #                    self.notify_uploader(page, subject, backlinks, item['user'])
    #                except mwclient.ProtectedPageError:
    #                    self.output('Warning! [[User talk:%s]] is protected!' % item['user'])

    #r_redirect = re.compile(ur'^\s*\#REDIRECT \[\[[Uu]ser[_ ]talk\:([^]|]*)\]\]')
    #def notify_uploader(self, page, subject, backlinks, user, from_redirect = False):
    #    if user in self.notification_blacklist: return
    #    if ('User talk:' + user) in backlinks: return

    #    self.output('Notifying %s of the deletion request of %s' % (user, subject))

    #    user_talk = self.site.Pages['User talk:' + user]
    #    # Check whether the user has editted the deletion request
    #    revisions = page.revisions(user = user, limit = 1)
    #    try:
    #        revisions.next()
    #    except StopIteration:
    #        pass
    #    else:
    #        return

    #    wait_token = self.site.wait_token()
    #    while True:
    #        try:
    #            text = user_talk.edit()
    #            if user_talk.redirect:
    #                if from_redirect:
    #                    return self.output('Warning! Double redirect found on User_talk:%s!' % user)
    #                return self.notify_uploader(page, subject, backlinks, user_talk.links(False)[0], True)

    #            text += '\n{{subst:User:DRBot/notify-uploader|%s}} ~~~~~' % subject
    #            user_talk.save(text, summary = 'Notification of deletion request of %s' % subject)
    #        except mwclient.EditError:
    #            try:
    #                self.site.wait(wait_token)
    #            except mwclient.MaximumRetriesExceeded:
    #                return self.output('Unable to report to %s.' % user)
    #        else:
    #            return



    #def set_archived_listing(self, year, month, day):
    #    self.cursor.execute("""UPDATE deletion_request_list
    #        SET archived = 1 WHERE year = ? AND month = ? AND 
    #        day = ?""", (year, month, day))
    #    self.database.commit()


    def run(self, iterator = None):
        self.read_listing()

    @staticmethod
    def normalize_title(title):
        title = title.strip(' \t\r\n_').replace('_', ' ')
        while title.count('  '):
            title = title.replace('  ', ' ')
        return title[0].upper() + title[1:]

    r_unsafe_wikilink = re.compile(ur'\[\[\s*([^:][^]]*)\s*\]\]')
    @classmethod
    def escape_wikilinks(self, text):
        return self.r_unsafe_wikilink.sub(self._escape_wikilink, text)

    @staticmethod
    def _escape_wikilink(match):
        return '[[:%s]]' % match.group(1)

    #@staticmethod
    #def output(message):
    #    print time.strftime('[%Y-%m-%d %H:%M:%S]'), message.encode('utf-8')

if __name__ == '__main__':

    try:

        parser = argparse.ArgumentParser( description = 'The SDBot' )
        parser.add_argument('--simulate', action='store_true', default=False, help='Do not write results to wiki')
        parser.add_argument('--debug', action='store_true', default=False, help='More verbose logging')
        args = parser.parse_args()

        file_handler = logging.handlers.RotatingFileHandler('sdbot.log', maxBytes=100000, backupCount=3)
        if args.debug:
            file_handler.setLevel(logging.DEBUG)
        else:
            file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        warn_handler = logging.FileHandler('warnings.log')
        warn_handler.setLevel(logging.WARNING)
        warn_handler.setFormatter(formatter)
        logger.addHandler(warn_handler)

        if args.simulate:
            console_handler = logging.StreamHandler()
            if args.debug:
                console_handler.setLevel(logging.DEBUG)
            else:
                console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            logger.info('Starting in simulate-mode')

        
        for loc in ['no_NO', 'nb_NO.utf8']:
            try:
                locale.setlocale(locale.LC_ALL, loc.encode('utf-8'))
                logger.info('Locale set to %s' % loc)
            except locale.Error:
                pass

        dr = SDBot(simulate = args.simulate)
        dr.run()
    
        runend = datetime.now()
        runtime = total_seconds(runend - runstart)
        logger.info('Runtime was %.f seconds.' % (runtime))

    except Exception as e:
        logger.exception('Unhandled Exception')

