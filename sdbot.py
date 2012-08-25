#encoding=utf-8
# python version 2.6.6, logging version 0.5.0.5 at nightshade
# python version 2.7.1, logging version 0.5.1.2 at willow
from __future__ import unicode_literals
from wp_private import sdbotlogin, mailfrom, mailto

import logging
import logging.handlers

from datetime import datetime
runstart = datetime.now()

import platform
pv = platform.python_version()
f = open('sdbot.log','a')
f.write('python v. %s, logging v. %s\n' % (pv, logging.__version__))
f.close()

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')

smtp_handler = logging.handlers.SMTPHandler( mailhost = ('localhost', 25),
                fromaddr = mailfrom, toaddrs = mailto, 
                subject=u"[toolserver] SDBot crashed!")
                
smtp_handler.setLevel(logging.ERROR)
logger.addHandler(smtp_handler)

file_handler = logging.FileHandler('sdbot.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def total_seconds(td):
    # for backwards compability. td is a timedelta object
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

#console_handler = logging.StreamHandler()
#console_handler.setLevel(logging.INFO)
#console_handler.setFormatter(formatter)
#logger.addHandler(console_handler)


import mwclient
import re
import locale
locale.setlocale(locale.LC_TIME, 'nb_NO.UTF-8'.encode('utf-8'))
# except locale.Error:

import sqlite3

from danmicholoparser import DanmicholoParser

"""
CREATE TABLE deletion_request_list (id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INT, month INT, day INT, archived BOOL);
CREATE TABLE notifications (id INTEGER PRIMARY KEY AUTOINCREMENT,
    deletion_request TEXT);
"""

class DeletionBot(object):

    def __init__(self):
        self.simulate = False

        self.site = mwclient.Site('no.wikipedia.org')
        self.site.login(*sdbotlogin)
        self.today = datetime.utcnow()

        self.archival_threshold = 86400
        #self.closure_threshold = 86400
        #self.notification_timeout = 86400

        #self.database = sqlite3.connect('delbot.db')
        #self.cursor = self.database.cursor()

        #page = self.site.Pages['User:%s/notification-blacklist' % self.site.username]
        #text = page.edit(readonly = True)
        #self.notification_blacklist = [i.strip() for i in text.split('\n')]
        #self.notification_blacklist = []

        # Temp. fix.
        page = self.site.Pages['Bruker:' + self.site.username]
        page.get_token('edit', True)

        self.admins = [i['name'] for i in self.site.allusers(group = 'sysop')]
        self.not_admin_closed = []

    r_deletion_request = re.compile(ur'\{\{[Ss]letteforslag[\s]*\|(.*?)(?:\|.*?)?\}\}')
    r_h2_heading = re.compile(ur'^\s*\=\=\s*(.*?)\s*\=\=\s*$', re.MULTILINE)
    def read_listing(self):

        page = self.site.Pages['Wikipedia:Sletting']

        logger.info('Reading deletion requests')

        monthyear = self.today.strftime('%B %Y') # e.g. "januar 2012"

        # Read from listing and normalize
        old_text = page.edit(section = 3)
        headings = self.r_h2_heading.findall(old_text)
        if len(headings) != 1 or headings[0].lower().find('liste over slettingskandidater') == -1:
            raise StandardError('Fant ikke den forventede overskriften på WP:S')

        deletion_requests = map(self.normalize_title, self.r_deletion_request.findall(re.sub('<\!--.+?-->', '', old_text)))
        statuses = {}

        # Loop over the requests
        archive_kept = []
        archive_deleted = []
        for request in deletion_requests[:]:
            archived = self.read_deletion_request('Wikipedia:Sletting/' + request)
            if archived:
                statuses[request] = archived['status']
                if archived['archive']:
                    #self.output('Archiving %s as %s' % (request, archived['status']))
                    deletion_requests.remove(request)
                    if archived['status'] in ['b','f','y']:
                        archive_kept.append(request)
                    else:
                        archive_deleted.append(request)

        if archive_kept or archive_deleted:
            summary = []
            if archive_kept:
                summary.append('%d diskusjon%s til [[Wikipedia:Sletting/Beholdt/%s]]' \
                        % (len(archive_kept), 'er' if len(archive_kept) > 1 else '', monthyear))
                # Save to archive
                wait_token = self.site.wait_token()
                while True:
                    try:
                        self.archive_requests('kept', archive_kept, monthyear, statuses)
                    except mwclient.InsufficientPermission:
                        raise
                    except mwclient.EditError:
                        self.site.wait(wait_token)
                    else:
                        break
            if archive_deleted:
                summary.append('%d diskusjon%s til [[Wikipedia:Sletting/Slettet/%s]]' % \
                        (len(archive_deleted), 'er' if len(archive_deleted) > 1 else '', monthyear))
                # Save to archive
                wait_token = self.site.wait_token()
                while True:
                    try:
                        self.archive_requests('deleted', archive_deleted, monthyear, statuses)
                    except mwclient.InsufficientPermission:
                        raise
                    except mwclient.EditError:
                        self.site.wait(wait_token)
                    else:
                        break
            summary = 'Arkiverer ' + ', '.join(summary)
        else:
            summary = 'Normaliserer'

        # Normalize & archive

        text = '== Liste over slettingskandidater (nyeste øverst) ==\n' \
            + '<!--  Legg inn nye {{sletteforslag|<navn på side>}} rett under denne linjen, øverst, ikke nederst -->'

        for request in deletion_requests:
            status = ''
            if request in statuses:
                status = '|' + statuses[request]
            text += '\n{{Sletteforslag|%s%s}}' % (request, status)
        if text != old_text:
            if self.simulate:
                print "--------" + page.name + ": " + summary + "------------"
                print text
            else:
                page.save(text, summary = summary)
 
    def archive_requests(self, archive, requests, monthyear, statuses):
        if archive == 'kept':
            page = self.site.Pages['Wikipedia:Sletting/Beholdt/%s' % monthyear]
            if not page.exists:
                text = '{{Arkivert|[[Wikipedia:Sletting]]}}\n{{Arkiv|{{Wikipedia:Sletting/Beholdt/Arkiv}}}}\n'
            else:
                text = page.edit()
        else:
            page = self.site.Pages['Wikipedia:Sletting/Slettet/%s' % monthyear]
            if not page.exists:
                text = '{{Arkivert|[[Wikipedia:Sletting]]}}\n{{Arkiv|{{Wikipedia:Sletting/Slettet/Arkiv}}}}\n'
            else:
                text = page.edit()

        # Archive
        text += '\n' + '\n'.join(('{{Sletteforslag|%s|%s}}' % (request, statuses[request]) for request in requests))

        # Save
        summary = 'Arkiverer %d diskusjon%s' % (len(requests), 'er' if len(requests) > 1 else '')
        if self.simulate:
            print "--------" + page.name + ": " + summary + "------------"
            print text
        else:
            page.save(text, summary = summary)

    r_h3_heading = re.compile(ur'^\s*\=\=\=\s*(.*?)\s*\=\=\=\s*$', re.MULTILINE)
    r_link = re.compile(ur'^\[\[[: ]*(.*)\s*\]\]$')
    def read_deletion_request(self, name):
        page = self.site.Pages[name]

        # Deletion request does not exist
        if not page.exists: 
            return False

        logger.info('Sjekker %s' % name)

        text = page.edit()
        # Find all headings
        headings = self.r_h3_heading.findall(text)
        # Either malformed or a mass deletion request
        if len(headings) != 1: 
            logger.warning('  either malformed or a mass deletion request, found %d h3 headers' % len(headings))
            return False

        # Find the subject
        m_subject = self.r_link.search(headings[0])

        # Malformed
        if not m_subject: 
            logger.warning('  malformed header: "%s" does not match "%s"' % (headings[0], m_subject))
            return False
        subject = self.normalize_title(m_subject.group(1))
        
        # Wrong heading
        if not re.search(ur'(?i)^Wikipedia\:Sletting\/%s$' % re.escape(subject), name): 
            logger.warning('  malformed header: "%s" , "%s"' % (name, subject))
            return False

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
        status = ''
        if len(decisions) > 0:
            logger.info('Fant %d avgjørelser: %s' % (len(decisions), ', '.join(decisions)))

            if decisions[-1] == 'beholdt':
                status = 'b'
            elif decisions[-1] == 'flettet':
                status = 'f'
            elif decisions[-1] == 'flyttet':
                status = 'y'
            elif decisions[-1] == 'hurtigsletta' or decisions[-1] == 'hurtigslettet':
                status = 'hs'
            elif decisions[-1] == 'omdirigert':
                status = 'o'
            elif decisions[-1] == 'slettet' or decisions[-1] == 'sletta':
                status = 's'

        # Checking for closedness
        if status != '': 
            last_rev = page.revisions(limit = 1).next()
            timedelta = self.today - datetime(*last_rev.get('timestamp')[:6])
            logger.info('    Status: %s, delta: %.f s' % (status, total_seconds(timedelta)))

            if status == 'b':
                page_subject = self.site.Pages[subject]
                firstrev = page.revisions(dir = 'newer', limit = 1).next()
                nomdate = datetime.strftime('%Y-%m-%d', firstrev['timestamp'])
                self.insert_kept(name, page, page_subject, nomdate)
                self.remove_template(name, page, page_subject)

            if total_seconds(timedelta) >= self.archival_threshold:
                # Check whether the last user was an admin
                if last_rev.get('user') not in self.admins and last_rev.get('user') != self.site.username:
                    logger.info('%s was closed by %s who is not an admin' % (page.name, last_rev.get('user')))
                    self.not_admin_closed.append((page.name, last_rev))
                logger.info('    Merker for arkivering')
                return { 'archive': True, 'status': status }
            else:
                return { 'archive': False, 'status': status }
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
        return False

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

    def insert_kept(self, name, page_nom, page_subject, nomination_date):
        if page_subject.namespace % 2 == 0:

            talk_page = self.site.Pages[self.get_talk(page_subject)]
            backlinks = page_nom.backlinks(generator = False)
            if talk_page.name in backlinks:
                logger.debug('  Deletion request is already backlinked')
                return

            logger.info('Inserting keep to %s' % page_subject.name)

            kept = '{{Sletting-beholdt | %s | %s }}' % (nomination_date, name)

            wait_token = self.site.wait_token()
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
                        self.site.wait(wait_token)
                    except mwclient.MaximumRetriesExceeded:
                        return logger.error('Unable to save page!')
                else:
                    return True

    def remove_template(self, name, page_nom, page_subject):

        backlinks = page_nom.backlinks(generator = False)
        if page_subject.name in backlinks:
            logger.info('Fjerner {{Sletting}} fra %s' % page_subject.name)

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

            wait_token = self.site.wait_token()
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
                        self.site.wait(wait_token)
                    except mwclient.MaximumRetriesExceeded:
                        return logger.error('Unable to save page')
                else:
                    return True

    #def set_archived_listing(self, year, month, day):
    #    self.cursor.execute("""UPDATE deletion_request_list
    #        SET archived = 1 WHERE year = ? AND month = ? AND 
    #        day = ?""", (year, month, day))
    #    self.database.commit()

    def save_not_admin_closed(self):
        listing = ['* [[:%s]] lukket av [[Bruker:%s|]] on %04i-%02i-%02i %02i:%02i:%02i' % \
                ((page_name, rev.get('user', '')) + rev['timestamp'][:6]) for page_name, rev in self.not_admin_closed]
        summary = '%s: %s diskusjoner' % (datetime.now().strftime('%Y-%m-%d'), len(listing))

        if listing:
            page = self.site.Pages['Bruker:DanmicholoBot/non-admin']
            text = page.edit()
            text += '\n\n== ~~~~~ ==\n%s' % '\n'.join(listing)
            if self.simulate:
                print "Skipping in simulate-mode"
            else:
                page.save(text, summary)

    def run(self, iterator = None):
        self.read_listing()
        self.save_not_admin_closed()

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

        import sys, os
        os.chdir(os.path.abspath(os.path.dirname(__file__)))

        dr = DeletionBot()
        dr.run()
    
        runend = datetime.now()
        runtime = total_seconds(runend - runstart)
        logger.info('Runtime was %.f seconds.' % (runtime))

    except Exception as e:
        logger.exception('Unhandled Exception')

