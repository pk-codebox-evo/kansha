#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare.i18n import _
from nagare import ajax, presentation, security

from .comp import CardMembers, Member


@presentation.render_for(CardMembers, 'action')
def render_card_members(self, h, comp, *args):
    """Member section view for card

    First members icons,
    Then icon "more user" if necessary
    And at the end icon "add user"
    """
    with h.div(class_='members'):
        h << h.script('''YAHOO.kansha.app.hideOverlay();''')
        for m in self.members[:self.MAX_SHOWN_MEMBERS]:
            h << m.on_answer(self.remove_member).render(h, model='overlay-remove')
        if len(self.members) > self.MAX_SHOWN_MEMBERS:
            h << h.div(self.see_all_members, class_='more')
        if self.overlay_add_members() is None:
            from kansha.toolbox import overlay
            self.overlay_add_members.becomes(overlay.Overlay(lambda r: (r.i(class_='ico-btn icon-user'), r.span(_(u'+'), class_='count')),
                                             lambda r: comp.render(r, 'add_member_overlay'), dynamic=True, cls='card-overlay'))
        h << h.div(self.overlay_add_members, class_='add')
    return h.root


@presentation.render_for(CardMembers, 'badge')
def render_members_badge(self, h, comp, model):
    model = 'action' if security.has_permissions('edit', self.card) else 'members_read_only'
    return comp.render(h, model)


@presentation.render_for(CardMembers, model='members_read_only')
def render_card_members_read_only(self, h, comp, *args):
    """Member section view for card

    First members icons,
    Then icon "more user" if necessary
    And at the end icon "add user"
    """
    with h.div(class_='members'):
        for m in self.members[:self.MAX_SHOWN_MEMBERS]:
            member = m.render(h, 'avatar')
            member.attrib.update({'class': 'miniavatar unselectable'})
            h << member
        if len(self.members) > self.MAX_SHOWN_MEMBERS:
            h << h.div(self.see_all_members, class_='more')
    return h.root


@presentation.render_for(CardMembers, 'members_list_overlay')
def render_members_members_list_overlay(self, h, comp, *args):
    """Overlay to list all members"""
    h << h.h2(_('All members'))
    # with h.form:
    with h.div(class_="members"):
        if security.has_permissions('edit', self.card):
            h << [m.on_answer(comp.answer).render(h, "remove") for m in self.members]
        else:
            h << [m.render(h, "avatar") for m in self.members]
    return h.root


def add_member(member_ext, member):
    member_ext.add_member(member)
    return "YAHOO.kansha.reload_cards['%s']();YAHOO.kansha.app.hideOverlay();" % member_ext.card.id


def add_members_by_email(member_ext, emails):
    member_ext.add_members_by_email(emails)
    return "YAHOO.kansha.reload_cards['%s']();YAHOO.kansha.app.hideOverlay();" % member_ext.card.id


@presentation.render_for(CardMembers, 'add_member_overlay')
def render_members_add_member_overlay(self, h, comp, *args):
    """Overlay to add member"""
    h << h.h2(_('Add members'))
    if self.favorites:
        with h.div(class_='favorites'):
            h << h.h3(_('Suggestions'))
            with h.ul:
                for favorite in self.favorites:
                    with h.li:
                        h << favorite.on_answer(lambda member: add_member(self, member))
    with h.div(class_='members search'):
        h << self.new_member.on_answer(lambda emails: add_members_by_email(self, emails))
    return h.root


@presentation.render_for(CardMembers, 'more_users')
def render_members_many_user(self, h, comp, *args):
    number = len(self.card.members) - self.MAX_SHOWN_MEMBERS
    return h.span(
        h.i(class_='ico-btn icon-user'),
        h.span(number, class_='count'),
        title=_('%s more...') % number)


@presentation.render_for(Member, 'board')
def render_member_board(self, h, comp, *args):
    application_url = h.request.application_url
    if security.has_permissions('manage', self.board):
        return self.user.on_answer(
            lambda action: self.dispatch(action, application_url)
        ).render(h, model=self.role)
    else:
        return h.div(self.user.render(h), class_='member')


@presentation.render_for(Member, 'board_overlay')
def render_member_board_overlay(self, h, comp, *args):
    application_url = h.request.application_url
    if security.has_permissions('manage', self.board):
        return self.user.on_answer(
            lambda action: self.dispatch(action, application_url)
        ).render(h, model='overlay-%s' % self.role)
    else:
        member = self.user.render(h, 'avatar')
        member.attrib.update({'class': 'avatar unselectable'})
        return member


@presentation.render_for(Member, 'favorite')
def render_member_friend(self, h, comp, *args):
    return self.user.on_answer(lambda email: comp.answer(self)).render(h, 'friend')


@presentation.render_for(Member, 'overlay-remove')
def render_member_overlay_remove(self, h, comp, model):
    return self.user.on_answer(lambda ret: comp.answer(self)).render(h, 'overlay-remove')
