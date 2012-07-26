

import mwclient
 
import re
import time, datetime
 
import sqlite3
 
"""
CREATE TABLE deletion_request_list (id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INT, month INT, day INT, archived BOOL);
CREATE TABLE notifications (id INTEGER PRIMARY KEY AUTOINCREMENT,
    deletion_request TEXT);
"""
 
class DeletionBot(object):
    def __init__(self):
        self.site = mwclient.ex.ConfiguredSite('.config', '.deletion_config')
        self.today = datetime.datetime.utcnow()
 
        self.database = sqlite3.connect(self.site.config['database'])
        self.cursor = self.database.cursor()
 
        page = self.site.Pages[u'User:%s/notification-blacklist' % self.site.username]
        text = page.edit(readonly = True)
        self.notification_blacklist = [i.strip() for i in text.split('\n')]
 
        # Temp. fix.
        page = self.site.Pages['User:' + self.site.username]
        page.get_token('edit', True)
 
        self.admins = [i['name'] for i in self.site.allusers(group = 'sysop')]
        self.not_admin_closed = []
 
 
    r_deletion_request = re.compile(ur'\{\{([Cc]ommons\:[Dd]eletion[ _]requests\/.*?)\}\}')
    def read_daily_listing(self, year, month, day):
 
        page = self.get_daily_listing(year, month, day)
        if not page: return
 
        self.output(u'Reading deletion requests from %04i-%02i-%02i' % (year, month, day))
 
        # Read from listing and normalize
        old_text = page.edit()
        deletion_requests = map(self.normalize_title, 
            self.r_deletion_request.findall(old_text))
 
        # Loop over the requests
        archive = []
        for request in deletion_requests[:]:
            archived = self.read_deletion_request(request, 
                (year, month, day))
            if archived:
                self.output(u'Archiving %s' % request)
                deletion_requests.remove(request)
                archive.append(request)
 
        if archive:
            summary = u'Archiving to ' + \
                '[[Commons:Deletion requests/Archive/%04i/%02i]]' % \
                (year, month)
            # Save to archive
            wait_token = self.site.wait_token()
            while True:
                try:
                    self.archive_requests(archive, year, month, day)
                except mwclient.InsufficientPermission:
                    raise
                except mwclient.EditError:
                    self.site.wait(wait_token)
                else:
                    break
        else:
            summary = u'Normalizing'
 
 
        if deletion_requests:
            # Normalize & archive
            text = time.strftime(u'== %s %s ==\n' % (self.months[month - 1], day))
            text += u'\n'.join((u'{{%s}}' % request for request in deletion_requests))
            if text != old_text:
                page.save(text, summary = summary, minor = True)
        elif page.exists and (year, month, day) < time.gmtime()[:3]:
            # Mark for deletion
            self.output(u'No more deletion requests from %04i-%02i-%02i left; requesting for deletion' % \
                (year, month, day))
            self.set_archived_listing(year, month, day)
            page.save(u'<noinclude>{{speedy delete|Empty listing}}</noinclude>', 
                summary + u'. Now empty: marking for speedy deletion.')
 
        else:
            # Already deleted
            self.set_archived_listing(year, month, day)
 
    def archive_requests(self, archive, year, month, day):
        page = self.site.Pages[u'Commons:Deletion requests/Archive/%04i/%02i' % \
            (year, month)]
        text = page.edit()
        # Find all headings
        days = re.split(ur'\=\=.?%s [0-9]{1,2}.?\=\=' % self.months[month - 1], text)
        # Set up the headings for this month
        days.extend((u'' for i in xrange(self.get_month_length(month, year) - len(days) + 1)))
 
        # Page heading
        days[0] = u'{{Deletion requests/Archive|%04i|%02i}}\n' % (year, month)
        # Archive
        days[day] += u'\n'.join((u'{{%s}}' % request for request in archive))
        # Compile
        text = days[0] + u'\n'.join((u'== %s %s ==\n' % (self.months[month - 1], i) + \
            days[i].strip() for i in xrange(1, len(days))))
        # Save
        page.save(text, summary = 'Archiving from Commons:Deletion requests/%04i/%02i/%02i' % \
            (year, month, day))
 
    r_h3_heading = re.compile(ur'^\s*\=\=\=\s*(.*?)\s*\=\=\=\s*$', re.MULTILINE)
    r_link = re.compile(ur'^\[\[[: ]*(.*)\s*\]\]$')
    def read_deletion_request(self, name, date):
        page = self.site.Pages[name]
 
        # Deletion request does not exist
        if not page.exists: return False
 
        self.output(u'Reading %s' % name)
 
        text = page.edit()
        # Find all headings
        headings = self.r_h3_heading.findall(text)
        # Either malformed or a mass deletion requesat
        if len(headings) != 1: return False
 
        # Find the subject
        m_subject = self.r_link.search(headings[0])
        # Malformed
        if not m_subject: return False
        subject = self.normalize_title(m_subject.group(1))
        # Wrong heading
        if not re.search(ur'(?i)^Commons\:Deletion requests\/%s$' % \
            re.escape(subject), name): return False
 
        self.notify_uploaders(page, subject)
 
        # Checking for closedness
        templates = list(page.templates(generator = False))
        if u'Template:DELheader' in templates and u'Template:DELfooter' in templates:
            timedelta = datetime.datetime.utcnow() - datetime.datetime(*page.touched[:6])
            if (timedelta.seconds + timedelta.days * 86400) >= self.site.config['archival_threshold']:
                # Check whether the last user was an admin
                last_rev = page.revisions(limit = 1).next()
                if last_rev.get('user') not in self.admins and last_rev.get('user') != self.site.username:
                    self.output(u'%s was closed by %s who is not an admin' % (page.name, last_rev.get('user')))
                    self.not_admin_closed.append((page.name, last_rev))
 
                self.output(u'Archiving %s' % name)
                page_subject = self.site.Pages[subject]
                if page_subject.exists:
                    self.insert_kept(name, page_subject, date)
                return True
        else:
            # Closing if deleted
            page_subject = self.site.Pages[subject]
            if not page_subject.exists:
                logevents = self.site.logevents(type = 'delete', title = subject)
                for event in logevents:
                    if event['action'] == 'delete':
                        timedelta = datetime.datetime.utcnow() - datetime.datetime(*event['timestamp'][:6])
                        if (timedelta.seconds + timedelta.days * 86400) >= self.site.config['closure_threshold']:
                            self.output(u'Closing %s' % name)
                            text = u'{{delh}}\n' + text
                            text += "\n----\n'''Deleted''' by [[User:%s|]]: ''%s''\n{{delf}}" % \
                                (event['user'], self.escape_wikilinks(event.get('comment', 
                                u'').replace('{{', '<nowiki>{{</nowiki>')))
                            try:
                                page.save(text, summary = u'Closing deletion request; its result was delete')
                            except mwclient.EditError, e:
                                self.output('Failed to close deletion request: %s' % e)
                            return False
        return False
 
 
    def notify_uploaders(self, page, subject):
        self.cursor.execute("""SELECT 1 FROM notifications WHERE
            deletion_request = ?""", (page.name, ))
        if self.cursor.fetchone(): return
 
        revisions = page.revisions(dir = 'newer', limit = 1, prop = 'timestamp')
        timedelta = datetime.datetime.utcnow() - datetime.datetime(*revisions.next()['timestamp'][:6])
 
        if (timedelta.seconds + timedelta.days * 86400) >= self.site.config['notification_timeout']:
            self.cursor.execute("""INSERT INTO notifications VALUES
                (NULL, ?)""", (page.name, ))
            self.database.commit()
 
            if subject.startswith(u'Image:'):
                image = self.site.Images[subject[6:]]
                backlinks = page.backlinks(generator = False)
 
                already_notified = [None]
                imageinfo = [image.imageinfo]
                imageinfo.extend(image.imagehistory())
                for item in imageinfo:
                    if 'user' in item and item.get('user') not in already_notified:
                        already_notified.append(item['user'])
                        try:
                            self.notify_uploader(page, subject, backlinks, item['user'])
                        except mwclient.ProtectedPageError:
                            self.output(u'Warning! [[User talk:%s]] is protected!' % item['user'])
 
    r_redirect = re.compile(ur'^\s*\#REDIRECT \[\[[Uu]ser[_ ]talk\:([^]|]*)\]\]')
    def notify_uploader(self, page, subject, backlinks, user, from_redirect = False):
        if user in self.notification_blacklist: return
        if (u'User talk:' + user) in backlinks: return
 
        self.output(u'Notifying %s of the deletion request of %s' % (user, subject))
 
        user_talk = self.site.Pages[u'User talk:' + user]
        # Check whether the user has editted the deletion request
        revisions = page.revisions(user = user, limit = 1)
        try:
            revisions.next()
        except StopIteration:
            pass
        else:
            return
 
        wait_token = self.site.wait_token()
        while True:
            try:
                text = user_talk.edit()
                if user_talk.redirect:
                    if from_redirect:
                        return self.output(u'Warning! Double redirect found on User_talk:%s!' % user)
                    return self.notify_uploader(page, subject, backlinks, user_talk.links(False)[0], True)
 
                text += '\n{{subst:User:DRBot/notify-uploader|%s}} ~~~~~' % subject
                user_talk.save(text, summary = u'Notification of deletion request of %s' % subject)
            except mwclient.EditError:
                try:
                    self.site.wait(wait_token)
                except mwclient.MaximumRetriesExceeded:
                    return self.output(u'Unable to report to %s.' % user)
            else:
                return
 
 
 
    @staticmethod
    def get_talk(page):
        if page.namespace == 0:
            return u'Talk:' + page.name
        ns, title = page.name.split(':', 1)
        return u'%s talk:%s' % (ns, title)
 
    def insert_kept(self, name, page_subject, (year, month, day)):
        if page_subject.namespace % 2 == 0:
            self.output(u'Inserting keep to %s' % page_subject.name)
 
            talk_page = self.site.Pages[self.get_talk(page_subject)]
            backlinks = page_subject.backlinks(generator = False)
            if talk_page.name in backlinks:
                self.output('Deletion request is already backlinked')
                return
 
            kept = u'{{kept|date=%02i %s %04i|discussion=%s}}\n' % \
                (day, self.months[month - 1], year, name)
 
            wait_token = self.site.wait_token()
            while True:
                try:
                    text = talk_page.edit()
                    talk_page.save(kept + text,
                        summary = u'Kept after [[%s|deletion request]]' % name)
                except mwclient.EditError, e:
                    try:
                        self.site.wait(wait_token)
                    except mwclient.MaximumRetriesExceeded:
                        return self.output(u'Unable to report to %s: %s' % (talk_page, e))
                else:
                    return True
 
 
    def get_daily_listing(self, year, month, day):
        self.cursor.execute("""SELECT archived FROM deletion_request_list
            WHERE year = ? AND month = ? AND day = ?""",
            (year, month, day))
        result = self.cursor.fetchone()
        if result == (1, ): return None
 
        timedelta = datetime.datetime.utcnow() - datetime.datetime(year, month, day)
        page = self.site.Pages['Commons:Deletion requests/%04i/%02i/%02i' % (year, month, day)]
        if result is None:
            if not page.exists and timedelta.days > 0:
                self.cursor.execute("""INSERT INTO deletion_request_list
                    VALUES (NULL, ?, ?, ?, 1)""", (year, month, day))
                self.database.commit()
                return None
            elif page.exists:
                self.cursor.execute("""INSERT INTO deletion_request_list
                    VALUES (NULL, ?, ?, ?, 0)""", (year, month, day))
                self.database.commit()
                return page
            else:
                raise StopIteration
        else:
            return page
    def set_archived_listing(self, year, month, day):
        self.cursor.execute("""UPDATE deletion_request_list
            SET archived = 1 WHERE year = ? AND month = ? AND 
            day = ?""", (year, month, day))
        self.database.commit()
 
    def save_not_admin_closed(self):
        listing = [u'* [[:%s]] closed by [[User:%s|]] on %04i-%02i-%02i %02i:%02i:%02i' % \
            ((page_name, rev.get('user', '')) + rev['timestamp'][:6]) for page_name, rev in self.not_admin_closed]
        summary = u'%s: %s items' % (time.strftime('%Y-%m-%d'), len(listing))
 
        if listing:
            page = self.site.Pages['User:DRBot/non-admin']
            text = page.edit()
            text += u'\n\n== ~~~~~ ==\n%s' % '\n'.join(listing)
            page.save(text, summary)
 
    def run(self, iterator = None):
        if not iterator:
            iterator = self.day_iterator(*self.site.config['start_date'])
        self.output(u'Running deletion bot')
        try:
            for date in iterator:
                self.read_daily_listing(*date)
        except StopIteration:
            pass
        self.save_not_admin_closed()
 
 
    @staticmethod
    def normalize_title(title):
        title = title.strip(u' \t\r\n_').replace(u'_', u' ')
        while title.count('  '):
            title = title.replace('  ', ' ')
        return title[0].upper() + title[1:]
 
    @staticmethod
    def get_month_length(self, month, year = 1):
        if month in (1, 3, 5, 7, 8, 10, 12):
            return 31
        elif month == 2:
            if year % 4 != 0:
                return 28
            if year % 400 == 0:
                return 28
            return 29
        else:
            return 30
    months = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December']
 
    r_unsafe_wikilink = re.compile(ur'\[\[\s*([^:][^]]*)\s*\]\]')
    @classmethod
    def escape_wikilinks(self, text):
        return self.r_unsafe_wikilink.sub(self._escape_wikilink, text)
    @staticmethod
    def _escape_wikilink(match):
        return u'[[:%s]]' % match.group(1)
 
    @classmethod
    def day_iterator(self, year, month, day):
        now = time.gmtime()[:3]
        while now >= (year, month, day):
            while month < 13:
                while day <= self.get_month_length(month, year):
                    if now < (year, month, day): return
 
                    yield year, month, day
                    day += 1
                day = 1
                month += 1
            month = 1
            year += 1
 
 
    @staticmethod
    def output(message):
        print time.strftime('[%Y-%m-%d %H:%M:%S]'), message.encode('utf-8')
 
if __name__ == '__main__':
    import sys, os
    os.chdir(os.path.abspath(os.path.dirname(__file__)))
 
    dr = DeletionBot()
 
    if '-today' in sys.argv:
        dr.run(DeletionBot.day_iterator(*time.gmtime()[:3]))
    else:
        dr.run()

