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
        self._favorites = []

        # members part of the card
        self.overlay_add_members = component.Component(
            overlay.Overlay(lambda r: (r.i(class_='ico-btn icon-user'), r.span(_(u'+'), class_='count')),
                            lambda r: component.Component(self).render(r, model='add_member_overlay'), dynamic=True, cls='card-overlay'))
        self.new_member = component.Component(usermanager.NewMember(self.autocomplete_method), model='add_members')
        self.members = [component.Component(usermanager.UserManager.get_app_user(member.user_username, data=member.user))
                        for member in DataMember.get_card_members(self.card.data)]

        self.see_all_members = component.Component(
            overlay.Overlay(lambda r: component.Component(self).render(r, model='more_users'),
                            lambda r: component.Component(self).on_answer(self.remove_member).render(r, model='members_list_overlay'),
                            dynamic=False, cls='card-overlay'))

    def autocomplete_method(self, value):
        """ """
        available_user_ids = self.get_available_user_ids()
        return [u for u in usermanager.UserManager.search(value) if u.id in available_user_ids]

    def get_available_user_ids(self):
        """Return ids of users who are authorized to be added on this card

        Return:
            - a set of user (UserData instance)
        """
        return self.get_all_available_user_ids() | self.get_pending_user_ids() - set(user.id for user in DataMember.get_card_members(self.card.data))

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

        # to be optimized later if still exists
        member_usernames = set(member.username for member in DataMember.get_card_members(self.card.data))
        board_user_stats = [(nb_cards, username) for username, nb_cards in self.member_stats.iteritems()]
        board_user_stats.sort(reverse=True)
        # Take the 5 most popular that are not already affected to this card
        favorites = [username for (__, username) in board_user_stats
                     if username not in member_usernames]
        self._favorites = [component.Component(usermanager.UserManager.get_app_user(username), "friend")
                           for username in favorites[:5]]
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

    def add_member(self, user_data):
        """Attach new member to card

        In:
          ``user_data`` -- UserData instance
        Return:
            - the new DataMember added
        """
        users = [member.user for member in DataMember.get_card_members(self.card.data)]
        if user_data not in users and user_data.id in self.get_available_user_ids():
            DataMember.add_card_member(self.card.data, user_data)
            log.debug('Adding %s to card %s', user_data.username, self.card.id)
            user = usermanager.UserManager.get_app_user(user_data.username, data=user_data)
            self.members.append(component.Component(user))
            values = {'user_id': user_data.username, 'user': user_data.fullname, 'card': self.card.get_title()}
            self.action_log.add_history(security.get_user(), u'card_add_member', values)

    def remove_member(self, username):
        """Remove member username from card member"""
        datauser = usermanager.UserManager.get_by_username(username)
        if not datauser:
            raise exceptions.KanshaException(_("User not found : %s" % username))
        log.debug('Removing %s from card %s', username, self.card.id)
        DataMember.remove_card_member(self.card.data, datauser)
        for member in self.members:
            if member().username == username:
                self.members.remove(member)
                values = {'user_id': member().username, 'user': member().data.fullname, 'card': self.card.get_title()}
                self.action_log.add_history(security.get_user(), u'card_remove_member', values)

    def has_permission_on_card(self, user, perm):
        granted = True
        if perm == 'edit':
            granted = user and (user.id in self.get_all_available_user_ids())
        return granted
