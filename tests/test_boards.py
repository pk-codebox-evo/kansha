# -*- coding:utf-8 -*-
#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

import unittest

from nagare import database
from elixir import metadata as __metadata__

from kansha import helpers
from kansha.board.models import DataBoard
from kansha.board import comp as board_module


database.set_metadata(__metadata__, 'sqlite:///:memory:', False, {})


class BoardTest(unittest.TestCase):

    def setUp(self):
        helpers.setup_db(__metadata__)
        self.boards_manager = helpers.get_boards_manager()

    def tearDown(self):
        helpers.teardown_db(__metadata__)

    def test_add_board(self):
        """Create a new board"""
        helpers.set_dummy_context()
        self.assertEqual(DataBoard.query.count(), 0)
        helpers.create_board()
        self.assertEqual(DataBoard.query.filter_by(is_template=False).count(), 1)

    def test_add_column_ok(self):
        """Add a column to a board"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        self.assertIsNotNone(board.archive_column)
        self.assertEqual(board.count_columns(), 4)
        board.create_column(0, helpers.word())
        self.assertEqual(board.count_columns(), 5)

    def test_add_column_ko(self):
        """Add a column with empty title to a board"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        self.assertEqual(board.count_columns(), 4)
        self.assertFalse(board.create_column(0, ''))

    def test_delete_column(self):
        """Delete column from a board"""
        helpers.set_dummy_context()
        user = helpers.create_user()
        helpers.set_context(user)
        board = helpers.create_board()
        self.assertIsNotNone(board.archive_column)
        self.assertEqual(board.count_columns(), 4)
        column = board.columns[0]
        board.delete_column(column)
        self.assertEqual(board.count_columns(), 3)

    def test_set_visibility_1(self):
        """Test set visibility method 1

        Initial State:
         - board:private
         - allow_comment: off
         - allow_votes: members

        End state
         - board:public
         - allow_comment: off
         - allow_votes: members
        """
        helpers.set_dummy_context()
        board = helpers.create_board()
        board.data.visibility = 0
        board.data.comments_allowed = 0
        board.data.votes_allowed = 1

        board.set_visibility(board_module.BOARD_PUBLIC)

        self.assertEqual(board.data.visibility, 1)
        self.assertEqual(board.data.comments_allowed, 0)
        self.assertEqual(board.data.votes_allowed, 1)

    def test_set_visibility_2(self):
        """Test set visibility method 2

        Initial State:
         - board:public
         - allow_comment: public
         - allow_votes: public

        End state
         - board:private
         - allow_comment: members
         - allow_votes: members
        """
        helpers.set_dummy_context()
        board = helpers.create_board()
        board.data.visibility = 1
        board.data.comments_allowed = 2
        board.data.votes_allowed = 2

        board.set_visibility(board_module.BOARD_PRIVATE)

        self.assertEqual(board.data.visibility, 0)
        self.assertEqual(board.data.comments_allowed, 1)
        self.assertEqual(board.data.votes_allowed, 1)

    def test_set_visibility_3(self):
        """Test set visibility method 3

        Initial State:
         - board:public
         - allow_comment: members
         - allow_votes: off

        End state
         - board:private
         - allow_comment: members
         - allow_votes: off
        """
        helpers.set_dummy_context()
        board = helpers.create_board()
        board.data.visibility = 1
        board.data.comments_allowed = 1
        board.data.votes_allowed = 0

        board.set_visibility(board_module.BOARD_PRIVATE)

        self.assertEqual(board.data.visibility, 0)
        self.assertEqual(board.data.comments_allowed, 1)
        self.assertEqual(board.data.votes_allowed, 0)

    def test_save_as_template(self):
        title = helpers.word()
        description = helpers.word()
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user()
        helpers.set_context(user)
        boards_manager = helpers.get_boards_manager()
        template = boards_manager.create_template_from_board(board, title, description, False)
        self.assertEqual(template.data.title, title)
        self.assertEqual(template.data.description, description)
        self.assertTrue(template.data.is_template)
        self.assertEqual(template.data.visibility, board_module.BOARD_PRIVATE)
        template = boards_manager.create_template_from_board(board, title, description, True)
        self.assertEqual(template.data.visibility, board_module.BOARD_PUBLIC)

    def test_switch_view(self):
        board = helpers.create_board()
        self.assertEqual(board.model, 'columns')
        board.switch_view()
        self.assertEqual(board.model, 'calendar')
        board.switch_view()
        self.assertEqual(board.model, 'columns')

    def test_get_by(self):
        '''Test get_by_uri and get_by_id methods'''
        helpers.set_dummy_context()
        orig_board = helpers.create_board()
        board = self.boards_manager.get_by_id(orig_board.id)
        self.assertEqual(orig_board.data.id, board.data.id)
        self.assertEqual(orig_board.data.title, board.data.title)
        board = self.boards_manager.get_by_uri(orig_board.data.uri)
        self.assertEqual(orig_board.data.id, board.data.id)
        self.assertEqual(orig_board.data.title, board.data.title)

    def test_card_to_document(self):
        helpers.set_dummy_context()
        user = helpers.create_user()
        helpers.set_context(user)
        board = helpers.create_board()
        column = board.create_column(1, u'test')
        card = column.create_card(u'test')
        doc = card.to_document(board.id)
        self.assertEqual(doc.title, card.data.title)
        self.assertEqual(doc.board_id, board.id)
        self.assertEqual(doc.archived, column.is_archive)
