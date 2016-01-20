# -*- coding:utf-8 -*-
#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare.i18n import _
from nagare import component, editor, i18n, security, var, validator as nagare_validator

from kansha import title
from kansha import events
from kansha import exceptions
from kansha.toolbox import popin, overlay
from kansha.card import comp

from .models import DataColumn


class Column(events.EventHandlerMixIn):

    """Column component
    """

    def __init__(self, id_, board, card_extensions, action_log, search_engine, services_service, data=None):
        """Initialization

        In:
            - ``id_`` -- the id of the column
        """
        self.db_id = id_
        self._data = data
        self.id = 'list_' + str(self.db_id)
        self.board = board
        self.nb_card = var.Var(self.data.nb_max_cards)
        self._services = services_service
        self.action_log = action_log
        self.search_engine = search_engine
        self.card_extensions = card_extensions
        self.body = component.Component(self, 'body')
        self.title = component.Component(
            title.EditableTitle(self.get_title)).on_answer(self.set_title)
        self.card_counter = component.Component(CardsCounter(self))
        self.cards = [
            component.Component(
                self._services(
                    comp.Card, c.id,
                    self.card_extensions,
                    self.action_log, data=c))
                      for c in self.data.cards]
        self.new_card = component.Component(
            comp.NewCard(self))

        self.actions_comp = component.Component(self, 'overlay')
        self.actions_overlay = component.Component(overlay.Overlay(
            lambda r: r.i(class_='icon-target2'),
            self.actions_comp.render,
            title=_('List actions'), dynamic=False))

    def update(self, other):
        self.data.update(other.data)
        self.nb_card = var.Var(self.data.nb_max_cards)
        cards_to_index = []
        for card_comp in other.cards:
            card = card_comp()
            new_card = self.create_card(card.get_title())
            new_card.update(card)
            cards_to_index.append(card)
        self.index_cards(cards_to_index, update=True)

    def index_cards(self, cards, update=False):
        for card in cards:
            scard = card.to_document(self.board.id)
            if update:
                self.search_engine.update_document(scard)
            else:
                self.search_engine.add_document(scard)
        self.search_engine.commit()

    def actions(self, action, comp):
        if action == 'delete':
            self.emit_event(comp, events.ColumnDeleted, comp)
        elif action == 'set_limit':
            self.card_counter.call(model='edit')
        elif action == 'purge':
            self.purge_cards()
        self.emit_event(comp, events.SearchIndexUpdated)

    def ui_create_card(self, comp, title):
        self.create_card(title)
        self.emit_event(comp, events.SearchIndexUpdated)

    def on_event(self, comp, event):
        if event.is_(events.CardClicked):
            card_comp = event.data
            card_comp.becomes(popin.Popin(card_comp, 'edit'))
        elif event.is_(events.ParentTitleNeeded):
            return self.get_title()
        elif event.is_(events.CardEditorClosed):
            card_bo = event.emitter
            slot = event.data
            slot.becomes(card_bo)
            # card has been edited, reindex
            self.search_engine.update_document(card_bo.to_document(self.board.id))
            self.search_engine.commit()
            self.emit_event(comp, events.SearchIndexUpdated)

    @property
    def data(self):
        """Return the column object from the database
        """
        if self._data is None:
            self._data = DataColumn.get(self.db_id)
        return self._data

    def __getstate__(self):
        self._data = None
        return self.__dict__

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
        if self.is_archive:
            return i18n._(u'Archived cards')
        return self.data.title

    def get_member_stats(self):
        """Return the most used users in this column

        Return:
            - a dictionary {'username', 'nb used'}
        """
        member_stats = {}
        for c in self.cards:
            # Test if c() is a Card instance and not Popin instance
            if isinstance(c(), comp.Card):
                for m in c().members:
                    username = m.username
                    member_stats[username] = member_stats.get(username, 0) + 1
        return member_stats

    def delete(self, purge=False):
        """Delete itself"""
        if purge:
            self.purge_cards()
        else:
            for card in self.cards:
                self.archive_card(card())
        DataColumn.delete_column(self.data)

    def remove_card(self, card):
        self.cards.pop(card.index)
        self.data.remove_card(card.data)

    def remove_card_by_id(self, card_id):
        """Remove card and return corresponding Component."""
        # find component
        card_comp = filter(lambda x: x().id == card_id, self.cards)[0]
        try:
            self.remove_card(card_comp())
        except (IndexError, ValueError):
            raise ValueError(u'Card has been deleted or does not belong to this list anymore')
        return card_comp

    def insert_card(self, index, card):
        self.data.insert_card(index, card.data)
        self.cards.insert(index, component.Component(card))

    def insert_card_comp(self, comp, index, card_comp):
        self.data.insert_card(index, card_comp().data)
        self.cards.insert(index, card_comp)
        card_comp.on_answer(self.handle_event, comp)

    def delete_card(self, card):
        """Delete card

        In:
            - ``card`` -- card to delete
        """
        self.cards.pop(card.index)
        values = {'column_id': self.id, 'column': self.get_title(), 'card': card.get_title()}
        card.action_log.add_history(
            security.get_user(),
            u'card_delete', values)
        self.search_engine.delete_document(card.schema, card.id)
        self.search_engine.commit()
        card.delete()
        self.data.delete_card(card.data)

    def purge_cards(self):
        for card_comp in self.cards:
            card = card_comp()
            values = {'column_id': self.id, 'column': self.get_title(), 'card': card.get_title()}
            card.action_log.add_history(
                security.get_user(),
                u'card_delete', values)
            self.search_engine.delete_document(card.schema, card.id)
            card.delete()
        del self.cards[:]
        self.search_engine.commit()
        self.data.purge_cards()

    def append_card(self, card):
        self.data.append_card(card.data)
        self.cards.append(component.Component(card))

    # FIXME: move to board only, use Events
    def archive_card(self, c):
        """Delete card

        In:
            - ``c`` -- card to delete
        """
        self.cards = [card for card in self.cards if c != card()]
        values = {'column_id': self.id, 'column': self.get_title(), 'card': c.get_title()}
        c.action_log.add_history(security.get_user(), u'card_archive', values)
        self.board.archive_card(c)

    def create_card(self, text=''):
        """Create a new card

        In:
            - ``text`` -- the title of the new card
        """
        if text:
            if not self.can_add_cards:
                raise exceptions.KanshaException(_('Limit of cards reached fo this list'))
            new_card = self.data.create_card(text, security.get_user().data)
            card_obj = self._services(comp.Card, new_card.id, self.card_extensions, self.action_log)
            self.cards.append(component.Component(card_obj, 'new'))
            values = {'column_id': self.id,
                      'column': self.get_title(),
                      'card': new_card.title}
            card_obj.action_log.add_history(
                security.get_user(),
                u'card_create', values)
            self.index_cards([card_obj])
            return card_obj

    def change_index(self, new_index):
        """Change index of the column

        In:
            - ``index`` -- new index
        """
        self.data.index = new_index

    def refresh(self):
        self.cards = [component.Component(
            self._services(comp.Card, data_card.id, self.card_extensions, self.action_log, data=data_card)
            ) for data_card in self.data.cards]

    def set_nb_cards(self, nb_cards):

        self.data.nb_max_cards = int(nb_cards) if nb_cards else None

    @property
    def can_add_cards(self):
        rval = True
        if self.nb_max_cards is not None:
            rval = self.count_cards < self.nb_max_cards
        return rval

    @property
    def nb_max_cards(self):
        return self.data.nb_max_cards

    @property
    def count_cards(self):
        return self.data.get_cards_count()

    @property
    def is_archive(self):
        return self.data.archive

    @is_archive.setter
    def is_archive(self, value):
        self.data.archive = value


class NewColumnEditor(object):

    """Column creator component
    """

    def __init__(self, columns_count):
        """Initialization

        In:
            - ``board`` -- the board the new column will belong
        """
        self.columns_count = columns_count
        self.index = editor.Property(u'').validate(nagare_validator.to_int)
        self.title = editor.Property(u'')
        self.title.validate(lambda v: nagare_validator.to_string(v).not_empty(_(u'''Can't be empty''')))
        self.nb_cards = editor.Property(u'').validate(self.validate_nb_cards)

    def is_validated(self):
        return all((
            self.index.error is None,
            self.title.error is None,
            self.nb_cards.error is None
        ))

    def validate_nb_cards(self, value):
        if value:
            return nagare_validator.to_int(value)
        return value

    def commit(self, comp):
        if self.is_validated():
            comp.answer((self.index.value, self.title.value, self.nb_cards.value))

    def cancel(self, comp):
        comp.answer(None)


class CardsCounter(object):

    def __init__(self, column):
        self.column = column
        self.id = self.column.id + '_counter'
        self.text = self.get_label()
        self.error = None

    def get_label(self):
        if self.column.nb_max_cards:
            label = str(self.column.count_cards) + '/' + str(self.column.nb_max_cards)
        else:
            label = str(self.column.count_cards)
        return label

    def change_nb_cards(self, text):
        """Change the title of our wrapped object

        In:
            - ``text`` -- the new title
        Return:
            - the new title

        """

        self.text = text
        self.column.set_nb_cards(text)
        return text

    def reset_error(self):
        self.error = None

    def cancel(self, comp):
        self.reset_error()
        comp.answer()

    def validate(self, text, comp):
        self.reset_error()
        nb = int(text) if text else 0
        count = self.column.count_cards
        if not nb:
            comp.answer(self.change_nb_cards(nb))
        elif nb >= count:
            comp.answer(self.change_nb_cards(nb))
        else:
            self.error = _('Must be bigger than %s') % count
