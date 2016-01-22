#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare.i18n import _
from peak.rules import when
from nagare import component, security, log

from kansha import exceptions
from kansha.toolbox import overlay
from kansha.user import usermanager
from kansha.cardextension import CardExtension
from kansha.services.actionlog.messages import render_event

from .models import DataMember

@when(render_event, "action=='card_add_member'")
def render_event_card_add_member(action, data):
    return _(u'User %(user)s has been assigned to card "%(card)s"') % data


@when(render_event, "action=='card_remove_member'")
def render_event_card_remove_member(action, data):
    return _(u'User %(user)s has been unassigned from card "%(card)s"') % data


class CardMembers(CardExtension):

    LOAD_PRIORITY = 90

    MAX_SHOWN_MEMBERS = 3

    def __init__(self, card, action_log, configurator):
        """
        Card is a card business object.
        """
        super(CardMembers, self).__init__(card, action_log, configurator)

        # members part of the card
        self.overlay_add_members = component.Component(None)
        self.new_member = component.Component(usermanager.NewMember(self.autocomplete_method), model='add_members')
        self.members = []
        for data_member in DataMember.get_card_members(self.card.data):
            self.members.append(component.Component(self._get_member_from_data(data_member)))

        self.see_all_members = component.Component(
            overlay.Overlay(lambda r: component.Component(self).render(r, model='more_users'),
                            lambda r: component.Component(self).on_answer(self.remove_member).render(r, model='members_list_overlay'),
                            dynamic=False, cls='card-overlay'))
        self._favorites = []

    def _get_member_from_data(self, data_member):
        app_user = usermanager.UserManager.get_app_user(data_member.user_username, data=data_member.user)
        return Member(app_user, self.configurator, data_member.role)

    def autocomplete_method(self, value):
        """ """
        available_user_ids = self.get_available_user_ids()
        return [u for u in usermanager.UserManager.search(value) if u.id in available_user_ids]

    def get_available_user_ids(self):
        """Return ids of users who are authorized to be added on this card

        Return:
            - a set of user (UserData instance)
        """
        return self.get_all_available_user_ids() | self.get_pending_user_ids() - set(member.user_username for member in DataMember.get_card_members(self.card.data))

    def get_all_available_user_ids(self):
        return self.configurator.get_available_user_ids() if self.configurator else []

    def get_pending_user_ids(self):
        return self.configurator.get_pending_user_ids() if self.configurator else []

    @property
    def member_stats(self):
        return self.configurator.get_member_stats() if self.configurator else {}

    @property
    def favorites(self):
        """Return favorites users for a given card

        Return:
            - list of favorites (User instances) wrappend on component
        """
        member_usernames = set(member().username for member in self.members)
        board_user_stats = [(nb_cards, username) for username, nb_cards in self.member_stats.iteritems()
                            if username not in member_usernames]
        board_user_stats.sort(reverse=True)
        favorites = [username for count, username in board_user_stats[:5]]
        members_dict = {data_member.user_username: data_member
                        for data_member in DataMember.get_board_members(self.configurator.data)
                        if data_member.user_username in favorites}
        favorites = [members_dict[username] for username in favorites]
        favorites = [self._get_member_from_data(favorite) for favorite in favorites]
        self._favorites = [component.Component(favorite, 'favorite') for favorite in favorites]
        return self._favorites

    def add_members(self, emails):
        """Add new members from emails

        In:
            - ``emails`` -- emails in string separated by "," or list of strings
        Return:
            - JS code, reload card and hide overlay
        """
        # Get all users with emails
        members = filter(None, map(usermanager.UserManager.get_by_email, emails))
        for new_data_member in members:
            self.add_member(new_data_member)

    def add_members_by_email(self, emails):
        members_by_email = {member().email: member() for member in self.members}
        for email in emails:
            member = members_by_email[email]
            self.add_member(member)

    def add_member(self, member):
        """Attach new member to card

        In:
          ``member`` -- Member instance
        """
        member.add_card(self.card)
        log.debug('Adding %s to card %s', member.username, self.card.id)
        self.members.append(component.Component(member))
        values = {'user_id': member.username, 'user': member.fullname, 'card': self.card.get_title()}
        self.action_log.add_history(security.get_user(), u'card_add_member', values)

    def remove_member(self, member):
        """Remove member from card"""
        member.remove_card(self.card)
        log.debug('Removing %s from card %s', member.username, self.card.id)
        for member_comp in self.members:
            if member_comp() is member:
                self.members.remove(member_comp)
        values = {'user_id': member.username, 'user': member.fullname, 'card': self.card.get_title()}
        self.action_log.add_history(security.get_user(), u'card_remove_member', values)

    def has_permission_on_card(self, user, perm):
        granted = True
        if perm == 'edit':
            granted = user and (user.id in self.get_all_available_user_ids())
        return granted


class Member(object):
    def __init__(self, user, board, role):
        self.user = component.Component(user)
        self.role = role
        self.board = board

    @property
    def data(self):
        return DataMember.get_by(board=self.board.data, user=self.user().data)

    def add_card(self, card):
        self.data.add_card(card.data)

    def remove_card(self, card):
        self.data.remove_card(card.data)

    def delete(self):
        return self.data.delete()

    @property
    def username(self):
        return self.user().username

    @property
    def fullname(self):
        return self.user().fullname

    @property
    def email(self):
        return self.user().email

    def dispatch(self, action, application_url):
        if action == 'remove':
            self.board.remove_board_member(self)
        elif action == 'toggle_role':
            role = u'manager' if self.role == u'member' else u'member'
            self.board.change_role(self, role)
            self.role = role
        elif action == 'resend':
            self.board.resend_invitation(self, application_url)