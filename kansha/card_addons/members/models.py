#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from elixir import Field, Unicode
from elixir import ManyToOne, ManyToMany, using_options

from kansha.models import Entity


class DataMember(Entity):
    using_options(tablename='members')

    board = ManyToOne('DataBoard', primary_key=True)
    user = ManyToOne('DataUser', primary_key=True)
    cards = ManyToMany('DataCard')
    role = Field(Unicode(255), default=lambda: u'')

    @property
    def fullname(self):
        return self.user.fullname

    # Board members
    @classmethod
    def get_board_users_by_role(cls, board, role):
        return cls.query.filter_by(board=board, role=role).all()

    @classmethod
    def get_board_managers(cls, board):
        return cls.get_board_users_by_role(board, u'manager')

    @classmethod
    def is_board_manager(cls, board, user):
        return cls.exists(board=board, user=user, role=u'manager')

    @classmethod
    def get_board_members(cls, board):
        return cls.query.filter_by(board=board).all()

    @classmethod
    def is_board_member(cls, board, user):
        return cls.exists(board=board, user=user)

    @classmethod
    def is_last_manager(cls, board, user):
        if not cls.is_board_manager(board, user):
            return False
        return cls.query.filter_by(board=board, role=u'manager').count() == 1

    @classmethod
    def add_board_user(cls, board, user, role=u''):
        member = cls.get_by(board=board, user=user)
        if member is None:
            member = cls(board=board, user=user, role=role)
        else:
            member.role = role
        return member

    @classmethod
    def remove_board_user(cls, board, user):
        member = cls.get_by(board=board, user=user)
        if member is not None:
            member.delete()

    @classmethod
    def change_board_user_role(cls, board, user, role=u''):
        member = cls.get_by(board=board, user=user)
        member.role = role

    @classmethod
    def get_board_member_stats(cls, board):
        q = cls.query.filter_by(board=board)
        ret = {}
        for member in q:
            ret[member.user_username] = ret.get(member.user_username, 0) + 1
        return ret

    # Card members
    @classmethod
    def get_card_members(cls, card):
        q = cls.query
        q = q.filter(cls.cards.contains(card))
        return q.all()

    def add_card(self, card):
        if not card in self.cards:
            self.cards.append(card)

    def remove_card(self, card):
        if card in self.cards:
            self.cards.remove(card)
