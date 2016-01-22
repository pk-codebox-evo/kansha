# -*- coding:utf-8 -*-
# --
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

import json
from functools import partial

from nagare.i18n import _
from peak.rules import when
from nagare.security import common
from nagare.database import session
from nagare import component, log, security, var

from kansha import title
from kansha.card import Card
from kansha.user import usermanager
from kansha.services import ActionLog
from kansha.column import comp as column
from kansha.user.comp import PendingUser
from kansha.toolbox import popin, overlay
from kansha.card_addons.label import Label
from kansha.authentication.database import forms
from kansha import events, exceptions, validator
from kansha.card_addons.members import DataMember, Member

from .models import DataBoard
from .boardconfig import BoardConfig
from .excel_export import ExcelExport
from .templates import SaveTemplateTask


# Board visibility
BOARD_PRIVATE = 0
BOARD_PUBLIC = 1

# Votes authorizations
VOTES_OFF = 0
VOTES_MEMBERS = 1
VOTES_PUBLIC = 2

# Comments authorizations
COMMENTS_OFF = 0
COMMENTS_MEMBERS = 1
COMMENTS_PUBLIC = 2

# WEIGHTING CARDS
WEIGHTING_OFF = 0
WEIGHTING_FREE = 1
WEIGHTING_LIST = 2


class Board(events.EventHandlerMixIn):

    """Board component"""

    MAX_SHOWN_MEMBERS = 4
    background_max_size = 3 * 1024  # in Bytes

    def __init__(self, id_, app_title, app_banner, theme, card_extensions, search_engine_service,
                 assets_manager_service, mail_sender_service, services_service,
                 load_children=True):
        """Initialization

        In:
          -- ``id_`` -- the id of the board in the database
          -- ``mail_sender_service`` -- Mail service, used to send mail
          -- ``on_board_delete`` -- function to call when the board is deleted
        """
        self.model = 'columns'
        self.app_title = app_title
        self.app_banner = app_banner
        self.theme = theme
        self.mail_sender = mail_sender_service
        self.id = id_
        self.assets_manager = assets_manager_service
        self.search_engine = search_engine_service
        self._services = services_service
        # Board extensions are not extracted yet, so
        # board itself implement their API.
        self.board_extensions = {
            'weight': self,
            'labels': self,
            'members': self,
            'comments': self,
            'votes': self
        }
        self.card_extensions = card_extensions.set_configurators(self.board_extensions)

        self.action_log = ActionLog(self)

        self.version = self.data.version
        self.modal = component.Component(popin.Empty())
        self.card_matches = set()  # search results
        self.last_search = u''

        self.columns = []
        self.archive_column = None
        self.members = []
        self.managers = []
        self.pending = []
        if load_children:
            self.load_children()

        # Member part
        self.overlay_add_members = component.Component(
            overlay.Overlay(lambda r: (r.i(class_='ico-btn icon-user'), r.span(_(u'+'), class_='count')),
                            lambda r: component.Component(self).render(r, model='add_member_overlay'),
                            dynamic=True, cls='board-labels-overlay'))
        self.new_member = component.Component(usermanager.NewMember(self.autocomplete_method))

        self.update_members()

        def many_user_render(h, number):
            return h.span(
                h.i(class_='ico-btn icon-user'),
                h.span(number, class_='count'),
                title=_("%s more...") % number)

        self.see_all_members = component.Component(overlay.Overlay(lambda r: many_user_render(r, len(self.all_members) - self.MAX_SHOWN_MEMBERS),
                                                                   lambda r: component.Component(self).render(r, model='members_list_overlay'),
                                                                   dynamic=False, cls='board-labels-overlay'))
        self.see_all_members_compact = component.Component(overlay.Overlay(lambda r: many_user_render(r, len(self.all_members)),
                                                                           lambda r: component.Component(self).render(r, model='members_list_overlay'),
                                                                           dynamic=False, cls='board-labels-overlay'))

        self.comp_members = component.Component(self)

        # Icons for the toolbar
        self.icons = {'add_list': component.Component(Icon('icon-plus', _('Add list'))),
                      'edit_desc': component.Component(Icon('icon-pencil', _('Edit board description'))),
                      'preferences': component.Component(Icon('icon-cog', _('Preferences'))),
                      'export': component.Component(Icon('icon-download3', _('Export board'))),
                      'save_template': component.Component(Icon('icon-floppy', _('Save as template'))),
                      'archive': component.Component(Icon('icon-trashcan', _('Archive board'))),
                      'leave': component.Component(Icon('icon-exit', _('Leave this board'))),
                      'history': component.Component(Icon('icon-history', _("Action log"))),
                      }

        # Title component
        self.title = component.Component(
            title.EditableTitle(self.get_title)).on_answer(self.set_title)

        self.must_reload_search = False

    @property
    def url(self):
        return self.data.url

    @classmethod
    def get_id_by_uri(cls, uri):
        board = DataBoard.get_by_uri(uri)
        board_id = None
        if board is not None:
            board_id = board.id
        return board_id

    @classmethod
    def exists(cls, **kw):
        return DataBoard.exists(**kw)

    # Main menu actions
    def add_list(self):
        new_column_editor = column.NewColumnEditor(len(self.columns))
        answer = self.modal.call(popin.Modal(new_column_editor))
        if answer:
            index, title, nb_cards = answer
            self.create_column(index, title, nb_cards if nb_cards else None)

    def edit_description(self):
        description_editor = BoardDescription(self.get_description())
        answer = self.modal.call(popin.Modal(description_editor))
        if answer is not None:
            self.set_description(answer)

    def save_template(self, comp):
        save_template_editor = SaveTemplateTask(self.get_title(),
                                                self.get_description(),
                                                partial(self.save_as_template, comp))
        self.modal.call(popin.Modal(save_template_editor))

    def show_actionlog(self):
        self.modal.call(popin.Modal(self.action_log))

    def show_preferences(self):
        preferences = BoardConfig(self)
        self.modal.call(popin.Modal(preferences))

    def save_as_template(self, comp, title, description, shared):
        data = (title, description, shared)
        return self.emit_event(comp, events.NewTemplateRequested, data)

    def copy(self, owner):
        """
        Create a new board that is a copy of self, without the archive.
        Children must be loaded.
        """
        new_data = self.data.copy()
        if self.data.background_image:
            new_data.background_image = self.assets_manager.copy(self.data.background_image)
        new_board = self._services(Board, new_data.id, self.app_title, self.app_banner, self.theme, self.card_extensions, load_children=False)
        new_board.add_member(owner, u'manager')

        assert(self.columns or self.data.is_template)
        cols = [col() for col in self.columns if not col().is_archive]
        for column in cols:
            new_column = new_board.create_column(-1, column.get_title())
            new_column.update(column)

        return new_board

    def on_event(self, comp, event):
        result = None
        if event.is_(events.ColumnDeleted):
            # actually delete the column
            result = self.delete_column(event.data)
        elif event.is_(events.CardArchived):
            result = self.archive_card(event.emitter)
        elif event.is_(events.SearchIndexUpdated):
            result = self.set_reload_search()
        elif event.is_(events.CardDisplayed):
            if self.must_reload_search:
                self.reload_search()
                result = 'reload_search'
            else:
                result = 'nop'

        return result

    def switch_view(self):
        self.model = 'calendar' if self.model == 'columns' else 'columns'

    def load_children(self):
        columns = []
        for c in self.data.columns:
            col = self._services(
                column.Column, c.id, self, self.card_extensions,
                self.action_log, data=c)
            if col.is_archive:
                self.archive_column = col
            columns.append(component.Component(col))

        self.columns = columns

    def increase_version(self):
        refresh = False
        self.version += 1
        self.data.increase_version()
        if self.data.version - self.version != 0:
            self.refresh()  # when does that happen?
            self.version = self.data.version
            refresh = True
        return refresh

    def refresh(self):
        print "refresh!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        print "if you see this message, please contact RTE."
        self.load_children()

    @property
    def all_members(self):
        return self.managers + self.members + self.pending

    def update_members(self):
        """Update members section

        Recalculate members + managers + pending
        Recreate overlays
        """
        self.members = []
        self.managers = []
        # TODO: remove access to DataMember when board-extensions are ready
        for member in DataMember.get_board_members(self.data):
            app_user = usermanager.UserManager.get_app_user(member.user_username, data=member.user)
            if member.role == u'manager':
                model = 'last_manager' if self.is_last_manager(app_user) else 'manager'
                self.managers.append(component.Component(Member(app_user, self, model), 'board'))
            else:
                self.members.append(component.Component(Member(app_user, self, 'member'), 'board'))
        self.pending = [component.Component(Member(PendingUser(token.token), self, 'pending'), 'board')
                        for token in self.data.pending]

    def set_title(self, title):
        """Set title

        In:
            - ``title`` -- new title
        """
        self.data.title = title

    def get_title(self):
        """Get title

        Return :
            - the board title
        """
        return self.data.title

    def mark_as_template(self, template=True):
        self.data.is_template = template

    def count_columns(self):
        """Return the number of columns
        """
        return len(self.columns)

    @security.permissions('edit')
    def create_column(self, index, title, nb_cards=None):
        """Create a new column in the board

        In:
            - ``index`` -- the position of the column as an integer
            - ``title`` -- the title of the new column
            - ``nb_cards`` -- the number of maximun cards on the colum
        """
        if index < 0:
            index = index + len(self.columns) + 1
        if title == '':
            return False
        col = self.data.create_column(index, title, nb_cards)
        col_obj = self._services(
            column.Column, col.id, self,
            self.card_extensions, self.action_log)
        self.columns.insert(
            index, component.Component(col_obj))
        self.increase_version()
        return col_obj

    @security.permissions('edit')
    def delete_column(self, col_comp):
        """Delete a board's column

        In:
            - ``id_`` -- the id of the column to delete
        """
        self.columns.remove(col_comp)
        col_comp().delete()
        self.increase_version()
        return popin.Empty()

    @security.permissions('edit')
    def update_card_position(self, data):
        data = json.loads(data)

        cols = {}
        for col in self.columns:
            cols[col().id] = (col(), col)

        orig, __ = cols[data['orig']]

        dest, dest_comp = cols[data['dest']]
        card_comp = orig.remove_card_by_id(data['card'])
        dest.insert_card_comp(dest_comp, data['index'], card_comp)
        card = card_comp()
        values = {'from': orig.get_title(),
                  'to': dest.get_title(),
                  'card': card.get_title()}
        self.action_log.for_card(card).add_history(
            security.get_user(),
            u'card_move', values)
        # reindex it in case it has been moved to the archive column
        card.add_to_index(self.search_engine, self.id, update=True)
        self.search_engine.commit()
        session.flush()

    @security.permissions('edit')
    def update_column_position(self, data):
        data = json.loads(data)
        cols = []
        found = None
        for col in self.columns:
            if col().id == data['list']:
                found = col
            else:
                cols.append(col)
        cols.insert(data['index'], found)
        for i, col in enumerate(cols):
            col().change_index(i)
        self.columns = cols
        session.flush()

    @property
    def visibility(self):
        return self.data.visibility

    def is_public(self):
        return self.visibility == BOARD_PUBLIC

    def set_visibility(self, visibility):
        """Changes board visibility

        If new visibility is "Member" and comments/votes permissions
        are in "Public" changes them to "Members"

        In:
         - ``visibility`` -- an integer, new visibility (Private or Public)
        """
        if self.comments_allowed == COMMENTS_PUBLIC:
            # If comments are PUBLIC that means the board was PUBLIC and
            # go to PRIVATE. That's why we don't test the visibility
            # input variable
            self.allow_comments(COMMENTS_MEMBERS)
        if self.votes_allowed == VOTES_PUBLIC:
            self.allow_votes(VOTES_MEMBERS)
        self.data.visibility = visibility

    @property
    def archived(self):
        return self.data.archived

    @property
    def show_archive(self):
        return self.data.show_archive

    @show_archive.setter
    def show_archive(self, value):
        self.data.show_archive = value
        self.set_reload_search()

    def archive_card(self, card):
        """Archive card

        In:
            - ``card`` -- card to archive
        """
        self.archive_column.append_card(card)
        self.archive_column.refresh()

    @property
    def weighting_cards(self):
        return self.data.weighting_cards

    def activate_weighting(self, weighting_type):
        if weighting_type == WEIGHTING_FREE:
            self.data.weighting_cards = 1
        elif weighting_type == WEIGHTING_LIST:
            self.data.weighting_cards = 2

        # reinitialize cards weights
        for col in self.columns:
            col = col().data
            for card in col.cards:
                card.weight = ''
        for card in self.archive_column.cards:
            card.weight = ''

    @property
    def weights(self):
        return self.data.weights

    @weights.setter
    def weights(self, weights):
        self.data.weights = weights

    def deactivate_weighting(self):
        self.data.weighting_cards = 0
        self.data.weights = ''

    def delete_clicked(self, comp):
        return self.emit_event(comp, events.BoardDeleted)

    def delete(self):
        """Deletes the board.
           Children must be loaded.
        """
        assert(self.columns)  # at least, contains the archive
        for column in self.columns:
            column().delete(purge=True)
        self.data.delete_history()
        session.refresh(self.data)
        self.data.delete()

        return True

    def archive(self, comp=None):
        """Archive the board
        """
        self.data.archived = True
        if comp:
            self.emit_event(comp, events.BoardArchived)
        return True

    def restore(self, comp=None):
        """Unarchive the board
        """
        self.data.archived = False
        if comp:
            self.emit_event(comp, events.BoardRestored)
        return True

    def leave(self, comp=None):
        """Children must be loaded."""
        # FIXME: all member management function should live in another component than Board.
        user = security.get_user()
        DataMember.remove_board_user(self.data, user.data)
        if not self.columns:
            self.load_children()
        if comp:
            self.emit_event(comp, events.BoardLeft)
        return True

    def export(self):
        return ExcelExport(self).download()

    @property
    def labels(self):
        """Returns the labels associated with the board
        """
        return [self._services(Label, data) for data in self.data.labels]

    @property
    def data(self):
        """Return the board object from database
        """
        return DataBoard.get(self.id)

    def allow_comments(self, v):
        """Changes permission to add comments

        In:
            - ``v`` -- a integer (see security.py for authorized values)
        """
        self.data.comments_allowed = v

    def allow_votes(self, v):
        """Changes permission to vote

        In:
            - ``v`` -- a integer (see security.py for authorized values)
        """
        self.data.votes_allowed = v

    @property
    def comments_allowed(self):
        return self.data.comments_allowed

    @property
    def votes_allowed(self):
        return self.data.votes_allowed

    # Callbacks for BoardDescription component
    def get_description(self):
        return self.data.description

    def set_description(self, value):
        self.data.description = value


    ##################
    # Member methods
    ##################

    def is_last_manager(self, user):
        """Return True if member is the last manager of the board

        In:
         - ``user`` -- member to test
        Return:
         - True if member is the last manager of the board
        """
        return DataMember.is_last_manager(self.data, user.data)

    def has_member(self, user):
        """Return True if user is member of the board

        In:
         - ``user`` -- user to test (User instance)
        Return:
         - True if user is member of the board
        """
        return DataMember.is_board_member(self.data, user.data)

    def has_manager(self, user):
        """Return True if user is manager of the board

        In:
         - ``user`` -- user to test (User instance)
        Return:
         - True if user is manager of the board
        """
        return DataMember.is_board_manager(self.data, user.data)

    def add_member(self, user, role=u'member'):
        """ Add new member to the board

        In:
         - ``user`` -- user to add (DataUser instance)
         - ``role`` -- role's member (manager or member)
        """
        DataMember.add_board_user(self.data, user.data, role)

    def remove_pending(self, member):
        # remove from pending list
        self.pending = [p for p in self.pending if p() != member]

        # remove invitation
        self.remove_invitation(member.username)

    def remove_member(self, member):
        # remove from members list
        if member.role == u'manager':
            self.managers = [p for p in self.managers if p() != member]
        else:
            self.members = [p for p in self.members if p() != member]
        member.delete()

    def remove_board_member(self, member):
        """Remove member from board

        Remove member from board. If member is PendingUser then remove
        invitation.

        Children must be loaded for propagation to the cards.

        In:
            - ``member`` -- Board Member instance to remove
        """
        if self.is_last_manager(member.user()):
            # Can't remove last manager
            raise exceptions.KanshaException(_("Can't remove last manager"))

        log.info('Removing member %s' % (member,))
        remove_method = {'pending': self.remove_pending,
                         'manager': self.remove_member,
                         'member': self.remove_member}
        remove_method[member.role](member)

        # remove member from columns
        # FIXME: this function should live in a board extension that has its own data and
        # should not rely on a full component tree.
        if not self.columns:
            self.load_children()

    def change_role(self, member, new_role):
        """Change member's role

        In:
            - ``member`` -- Board member instance
            - ``new_role`` -- new role
        """
        log.info('Changing role of %s to %s' % (member, new_role))
        user = member.user()
        if self.is_last_manager(user):
            raise exceptions.KanshaException(_("Can't remove last manager"))

        DataMember.change_board_user_role(self.data, user.data, new_role)
        self.update_members()

    def remove_invitation(self, email):
        """ Remove invitation

        In:
         - ``email`` -- guest email to invalidate
        """
        for token in self.data.pending:
            if token.username == email:
                token.delete()
                session.flush()
                break

    def invite_members(self, emails, application_url):
        """Invite somebody to this board,

        Create token used in invitation email.
        Store email in pending list.

        Params:
            - ``emails`` -- list of emails
        """
        for email in set(emails):
            # If user already exists add it to the board directly or invite it otherwise
            invitation = forms.EmailInvitation(self.app_title, self.app_banner, self.theme, email, security.get_user(), self, application_url)
            invitation.send_email(self.mail_sender)

    def resend_invitation(self, pending_member, application_url):
        """Resend an invitation,

        Resend invitation to the pending member

        In:
            - ``pending_member`` -- Send invitation to this user (PendingMember instance)
        """
        email = pending_member.username
        invitation = forms.EmailInvitation(self.app_title, self.app_banner, self.theme, email, security.get_user(), self, application_url)
        invitation.send_email(self.mail_sender)
        # re-calculate pending
        self.pending = [component.Component(Member(PendingUser(token.token), self, 'pending'), 'board')
                        for token in set(self.data.pending)]

################

    def autocomplete_method(self, v):
        """ Method called by autocomplete component.

        This method is called when you search a user on the add member
        overlay int the field autocomplete

        In:
            - ``v`` -- first letters of the username
        Return:
            - list of user (User instance)
        """
        users = usermanager.UserManager.search(v)
        results = []
        for user in users:
            if user.is_validated() and user.email not in [m().email for m in self.all_members]:
                results.append(user)
        return results

    def get_last_activity(self):
        return self.action_log.get_last_activity()

    def get_friends(self, user):
        """Return user friends for the current board

        Returned users which are not board's member and have not pending invitation

        Return:
         - list of user's friends (User instance) wrapped on component
        """
        already_in = set([m().email for m in self.all_members])
        best_friends = user.best_friends(already_in, 5)
        self._best_friends = [component.Component(usermanager.UserManager.get_app_user(u.username), "friend") for u in best_friends]
        return self._best_friends

    def get_member_stats(self):
        """Return the most used users in this column.

        Ask most used users to columns

        Return:
            - a dictionary {'username', 'nb used'}
        """
        return DataMember.get_board_member_stats(self.data)

    def get_available_user_ids(self):
        """Return list of member

        Return:
            - list of members
        """
        # TODO: remove access to DataMember when board-extensions are ready
        members = DataMember.get_board_members(self.data)
        return set(dbm.user_username for dbm in members)

    def get_pending_user_ids(self):
        return set(user.id for user in self.data.get_pending_users())

    def set_background_image(self, new_file):
        """Set the board's background image
        In:
            - ``new_file`` -- the background image (FieldStorage)
        Return:
            nothing
        """
        if new_file is not None:
            fileid = self.assets_manager.save(new_file.file.read(),
                                              metadata={'filename': new_file.filename,
                                                        'content-type': new_file.type})
            self.data.background_image = fileid
        else:
            self.data.background_image = None

    def set_background_position(self, position):
        self.data.background_position = position

    @property
    def background_image_url(self):
        img = self.data.background_image
        try:
            return self.assets_manager.get_image_url(img, include_filename=False) if img else None
        except IOError:
            log.warning('Missing background %r for board %r', img, self.id)
            return None

    @property
    def background_image_position(self):
        return self.data.background_position or 'center'

    @property
    def title_color(self):
        return self.data.title_color

    def set_title_color(self, value):
        self.data.title_color = value or u''

    def search(self, query):
        self.last_search = query
        if query:
            condition = Card.schema.match(query) & (Card.schema.board_id == self.id)
            # do not query archived cards if archive column is hidden
            if not self.show_archive:
                condition &= (Card.schema.archived == False)
            self.card_matches = set(doc._id for (_, doc) in self.search_engine.search(condition))
            # make the difference between empty search and no results
            if not self.card_matches:
                self.card_matches.add(None)
        else:
            self.card_matches = set()

    @staticmethod
    def get_all_board_ids():
        return DataBoard.get_all_board_ids()

    @staticmethod
    def get_templates_for(user_username, user_source):
        return DataBoard.get_templates_for(user_username, user_source, BOARD_PUBLIC)

    def set_reload_search(self):
        self.must_reload_search = True

    def reload_search(self):
        self.must_reload_search = False
        return self.search(self.last_search)

################


class Icon(object):

    def __init__(self, icon, title=None):
        """Create icon object

        In:
          - ``icon`` -- icon class name (use icomoon custom font)
          - ``title`` -- icon title (and alt)
        """
        self.icon = icon
        self.title = title

################


class BoardDescription(object):

    """Description component
    """

    def __init__(self, description):
        """Initialization

        In:
            - ``description`` -- callable that returns the description.
        """
        self.description = var.Var(description)

    def commit(self, comp):
        description = self.description().strip()
        if description:
            description = validator.clean_text(description)
        comp.answer(description)

    def cancel(self, comp):
        comp.answer(None)


# TODO: move this to board extension
@when(common.Rules.has_permission, "user and perm == 'Add Users' and isinstance(subject, Board)")
def has_permission_Board_add_users(self, user, perm, board):
    """Test if users is one of the board's managers, if he is he can add new user to the board"""
    return board.has_manager(user)
