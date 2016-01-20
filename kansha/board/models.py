# -*- coding:utf-8 -*-
# --
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

import uuid
import urllib

from elixir import using_options
from elixir import ManyToOne, OneToMany
from elixir import Field, Unicode, Integer, Boolean, UnicodeText

from kansha.models import Entity
from nagare.database import session
from kansha.user.models import DataUser
from kansha.column.models import DataColumn
from kansha.card_addons.label import DataLabel
from kansha.card_addons.members import DataMember


class DataBoard(Entity):
    """Board mapper

     - ``title`` -- board title
     - ``is_template`` -- is this a real board or a template?
     - ``columns`` -- list of board columns
     - ``labels`` -- list of labels for cards
     - ``comments_allowed`` -- who can comment ? (0 nobody, 1 board members only , 2 all application users)
     - ``votes_allowed`` -- who can vote ? (0 nobody, 1 board members only , 2 all application users)
     - ``description`` -- board description
     - ``visibility`` -- board visibility (0 Private, 1 Public)
     - ``members`` -- list of members (simple members and manager)
     - ``managers`` -- list of managers
     - ``uri`` -- board URI (Universally Unique IDentifier)
     - ``last_users`` -- list of last users
     - ``pending`` -- invitations pending for new members (use token)
     - ``archive`` -- display archive column ? (0 false, 1 true)
     - ``archived`` -- is board archived ?
    """
    using_options(tablename='board')
    title = Field(Unicode(255))
    is_template = Field(Boolean, default=False)
    columns = OneToMany('DataColumn', order_by="index",
                        cascade='delete')
    labels = OneToMany('DataLabel', order_by='index')
    comments_allowed = Field(Integer, default=1)
    votes_allowed = Field(Integer, default=1)
    description = Field(UnicodeText, default=u'')
    visibility = Field(Integer, default=0)
    version = Field(Integer, default=0, server_default='0')
    uri = Field(Unicode(255), index=True, unique=True)
    last_users = ManyToOne('DataUser', order_by=('fullname', 'email'))
    pending = OneToMany('DataToken', order_by='username')
    history = OneToMany('DataHistory')

    background_image = Field(Unicode(255))
    background_position = Field(Unicode(255))
    title_color = Field(Unicode(255))
    show_archive = Field(Integer, default=0)
    archived = Field(Boolean, default=False)

    weighting_cards = Field(Integer, default=0)
    weights = Field(Unicode(255), default=u'')

    @property
    def template_title(self):
        # TODO: move to board extension
        managers = DataMember.get_board_managers(self)
        if not managers or self.visibility == 0:
            return self.title
        return u'{0} ({1})'.format(self.title, managers[0].fullname)

    @property
    def managers(self):
        return DataMember.get_board_managers(self)

    def copy(self):
        new_data = DataBoard(title=self.title,
                             description=self.description,
                             background_position=self.background_position,
                             title_color=self.title_color,
                             comments_allowed=self.comments_allowed,
                             votes_allowed=self.votes_allowed,
                             weighting_cards=self.weighting_cards,
                             weights=self.weights)
        session.flush()
        # TODO: move to board extension
        for label in self.labels:
            new_data.labels.append(label.copy())
        session.flush()
        return new_data

    def get_label_by_title(self, title):
        return (l for l in self.labels if l.title == title).next()

    def delete_history(self):
        for event in self.history:
            session.delete(event)
        session.flush()

    def increase_version(self):
        self.version += 1
        if self.version > 2147483600:
            self.version = 1

    @property
    def url(self):
        return urllib.quote_plus(
            "%s/%s" % (self.title.encode('ascii', 'ignore'), self.uri),
            '/'
        )

    def __init__(self, *args, **kwargs):
        """Initialization.

        Create board and uri of the board
        """
        super(DataBoard, self).__init__(*args, **kwargs)
        self.uri = unicode(uuid.uuid4())

    @classmethod
    def get_by_id(cls, id):
        return cls.get(id)

    @classmethod
    def get_by_uri(cls, uri):
        return cls.get_by(uri=uri)

    def get_pending_users(self):
        emails = [token.username for token in self.pending]
        return DataUser.query.filter(DataUser.email.in_(emails))

    def set_background_image(self, image):
        self.background_image = image or u''

    @classmethod
    def get_all_board_ids(cls):
        return session.query(cls.id).filter_by(is_template=False).order_by(cls.title)

    @classmethod
    def get_templates_for(cls, user_username, user_source, public_value):
        q = cls.query
        q = q.filter(cls.archived == False)
        q = q.filter(cls.is_template == True)
        q = q.order_by(cls.title)

        q1 = q.filter(cls.visibility == public_value)

        q2 = q.join(DataMember)
        q2 = q2.filter_by(user_username=user_username, user_source=user_source, role=u'manager')
        q2 = q2.filter(cls.visibility != public_value)

        return q1, q2

    def create_column(self, index, title, nb_cards=None, archive=False):
        return DataColumn.create_column(self, index, title, nb_cards, archive)

    def create_label(self, title, color):
        label = DataLabel(title=title, color=color)
        self.labels.append(label)
        session.flush()
        return label


# Populate
DEFAULT_LABELS = (
    (u'Green', u'#22C328'),
    (u'Red', u'#CC3333'),
    (u'Blue', u'#3366CC'),
    (u'Yellow', u'#D7D742'),
    (u'Orange', u'#DD9A3C'),
    (u'Purple', u'#8C28BD')
)


def create_template_empty():
    board = DataBoard(title=u'Empty board', is_template=True, visibility=1)
    for title, color in DEFAULT_LABELS:
        board.create_label(title=title, color=color)
    session.flush()
    return board


def create_template_todo():
    board = DataBoard(title=u'Todo', is_template=True, visibility=1)
    for index, title in enumerate((u'To Do', u'Doing', u'Done')):
        board.create_column(index, title)
    for title, color in DEFAULT_LABELS:
        board.create_label(title=title, color=color)
    session.flush()
    return board
