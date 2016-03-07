import json
import string
import requests
import re
from trac.core import Component, implements
from trac.config import Option
from trac.ticket.api import ITicketChangeListener


CONT = ' _etc._'


def prepare_ticket_values(ticket, action=None):
    values = ticket.values.copy()
    values['id'] = "#" + str(ticket.id)
    values['action'] = action
    values['url'] = ticket.env.abs_href.ticket(ticket.id)
    values['project'] = ticket.env.project_name.encode('utf-8').strip()
    values['attrib'] = ''
    values['changes'] = ''
    return values


def truncate(value, n):
    value = unicode(value)
    return value if len(value) <= n else (value[:n - len(CONT)] + CONT)


class SlackNotifcationPlugin(Component):
    implements(ITicketChangeListener)
    emoji = {
        'closed': 'heavy_check_mark',
        'created': 'pushpin',
        'changed': 'pencil2',
        'assigned': 'point_right',
        'needsintegrating': 'arrow_heading_down',
        'needstesting': 'passport_control',
        'reopened': 'arrows_counterclockwise',
        'testing': 'customs',
    }
    webhook = Option('slack', 'webhook',
                     'https://hooks.slack.com/services/',
                     doc="Incoming webhook for slack")
    channel = Option('slack', 'channel',
                     '#Trac', doc="Channel name on slack")
    username = Option('slack', 'username',
                      'Trac-Bot', doc="Username of the bot on slack notify")
    fields = Option('slack', 'fields', 'type,component,resolution')

    def notify(self, type, values):
        values['author'] = re.sub(r' <.*', '', values['author'])
        values['emoji'] = self.emoji.get(values['action'],
                                         'incoming_envelope')
        values['maybe_status'] = (
            values['status'] + ' '
            if values['action'] != values['status'] else ''
        )
        values['maybe_owner'] = (
            values['owner'] + u'\u2019s ' if values['owner'] else ''
        )

        if values['action'] == 'created':
            values['ticket_link'] = '<%(url)s|%(type)s %(id)s %(summary)s>'
            template = ':%(emoji)s: %(ticket_link)s created by @%(author)s'
        else:
            values['ticket_link'] = '<%(url)s|%(id)s>'
            template = ':%(emoji)s: %(maybe_owner)s%(maybe_status)s %(ticket_link)s %(action)s by @%(author)s'
            if values['comment']:
                template += ': %(comment)s'

        message = template % values
        data = {
            "channel": self.channel,
            "username": self.username,
            "text": message.encode('utf-8').strip()
        }

        try:
            requests.post(self.webhook, data={"payload": json.dumps(data)})
        except requests.exceptions.RequestException:
            return False
        return True

    def ticket_created(self, ticket):
        values = prepare_ticket_values(ticket, 'created')
        values['author'] = values['reporter']
        values['comment'] = ''
        fields = self.fields.split(',')
        attrib = []

        for field in fields:
            if ticket[field] != '':
                attrib.append('  * %s: %s' % (field, ticket[field]))

        values['attrib'] = "\n".join(attrib) or ''

        self.notify('ticket', values)

    def ticket_changed(self, ticket, comment, author, old_values):
        action = 'changed'
        try:
            if ticket.values['status'] != old_values['status']:
                action = 'moved to ' + ticket.values['status']
        except KeyError:
            pass
        values = prepare_ticket_values(ticket, action)
        comment = truncate(next(iter(filter(bool, map(string.strip,
                                comment.splitlines()))), ''), 100)
        values.update({
            'comment': comment or '',
            'author': author or '',
            'old_values': old_values
        })

        if 'description' not in old_values.keys():
            values['description'] = ''

        fields = self.fields.split(',')
        changes = []
        attrib = []

        for field in fields:
            if ticket[field] != '':
                attrib.append('  * %s: %s' % (field, ticket[field]))

            if field in old_values.keys():
                changes.append('  * %s: %s => %s' %
                               (field, old_values[field], ticket[field]))

        values['attrib'] = "\n".join(attrib) or ''
        values['changes'] = "\n".join(changes) or ''

        self.notify('ticket', values)

    def ticket_deleted(self, ticket):
            pass

    # def wiki_page_added(self, page):
    # def wiki_page_changed(self, page, version, t, comment, author, ipnr):
    # def wiki_page_deleted(self, page):
    # def wiki_page_version_deleted(self, page):
