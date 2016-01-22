# -*- coding:utf-8 -*-
#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare import component, i18n, security
from nagare.namespaces import xhtml5

from kansha import helpers
from kansha.board import BOARD_PRIVATE, BOARD_PUBLIC
from kansha.cardextension.tests import CardExtensionTestCase

from .comp import CardMembers
from .models import DataMember


class CardMembersTest(CardExtensionTestCase):

    extension_name = 'members'
    extension_class = CardMembers

    def test_has_member_1(self):
        """Test has member 1"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user()
        helpers.set_context(user)
        DataMember.add_board_user(board.data, user.data)
        self.assertTrue(board.has_member(user))

    def test_has_member_2(self):
        """Test has member 2"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user('bis')
        helpers.set_context(user)
        user_2 = helpers.create_user(suffixe='2')
        DataMember.add_board_user(board.data, user_2.data, u'manager')
        self.assertFalse(board.has_member(user))

    def test_has_manager_1(self):
        """Test has manager 1"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user('bis')
        helpers.set_context(user)
        self.assertFalse(board.has_manager(user))
        DataMember.add_board_user(board.data, user.data, u'manager')
        self.assertTrue(board.has_manager(user))

    def test_has_manager_2(self):
        """Test has manager 2"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user('bis')
        helpers.set_context(user)
        user_2 = helpers.create_user(suffixe='2')
        self.assertFalse(board.has_manager(user))
        DataMember.add_board_user(board.data, user_2.data, u'manager')
        self.assertFalse(board.has_manager(user))

    def test_add_member_1(self):
        """Test add member"""
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user('bis')
        helpers.set_context(user)
        self.assertFalse(board.has_member(user))
        DataMember.add_board_user(board.data, user.data, u'member')
        self.assertTrue(board.has_member(user))

    def test_change_role(self):
        '''Test change role'''
        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user('test')
        DataMember.add_board_user(board.data, user.data)
        board.update_members()

        def find_board_member():
            for member in board.all_members:
                if member().username == user.username:
                    return member()

        member = find_board_member()
        self.assertEqual(len(board.members), 1)
        self.assertEqual(len(board.managers), 1)

        member.dispatch('toggle_role', '')
        member = find_board_member()
        board.update_members()
        self.assertEqual(len(board.members), 0)
        self.assertEqual(len(board.managers), 2)

        member.dispatch('toggle_role', '')
        board.update_members()
        self.assertEqual(len(board.members), 1)
        self.assertEqual(len(board.managers), 1)

    def test_view_board_1(self):
        """Test security view board 1

        Board Private
        User not logged
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        helpers.set_context()  # real security manager for tests
        self.assertFalse(security.has_permissions('view', board))

    def test_view_board_2(self):
        """Test security view board 2

        Board Public
        User not logged
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        board.set_visibility(BOARD_PUBLIC)
        user = helpers.create_user('bis')
        helpers.set_context(user)
        self.assertTrue(security.has_permissions('view', board))

    def test_view_board_3(self):
        """Test security view board 3

        Board Private
        User logged but not member of the board
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        board.set_visibility(BOARD_PRIVATE)
        user = helpers.create_user('bis')
        helpers.set_context(user)
        self.assertFalse(security.has_permissions('view', board))

    def test_view_board_4(self):
        """Test security view board 4

        Board Private
        User member of the board
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        board.set_visibility(BOARD_PRIVATE)
        user = helpers.create_user('bis')
        helpers.set_context(user)
        DataMember.add_board_user(board.data, user.data, u'member')
        self.assertTrue(security.has_permissions('view', board))

    def test_view_board_5(self):
        """Test security view board 5

        Board Public
        User member of the board
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        board.set_visibility(BOARD_PUBLIC)
        user = helpers.create_user('bis')
        helpers.set_context(user)
        DataMember.add_board_user(board.data, user.data, u'member')
        self.assertTrue(security.has_permissions('view', board))

    def test_rendering_security_view_board_2(self):
        """Test rendering security view board 2

        Test rendering (Board private / user member)
        """
        helpers.set_dummy_context()  # to be able to create board
        board = helpers.create_board()
        board.set_visibility(BOARD_PRIVATE)
        user = helpers.create_user('bis')
        helpers.set_context(user)
        DataMember.add_board_user(board.data, user.data, u'member')
        with i18n.Locale('en', 'US'):
            component.Component(board).on_answer(lambda x: None).render(xhtml5.Renderer())

    def test_get_boards(self):
        '''Test get boards methods'''

        helpers.set_dummy_context()
        board = helpers.create_board()
        user = helpers.create_user()
        user2 = helpers.create_user('bis')
        board.add_member(user2, u'member')
        boards_manager = helpers.get_boards_manager()
        self.assertTrue(board.has_manager(user))
        self.assertFalse(board.has_manager(user2))

        helpers.set_context(user)
        boards_manager.load_user_boards()
        self.assertNotIn(board.id, boards_manager.last_modified_boards)
        self.assertNotIn(board.id, boards_manager.guest_boards)
        self.assertIn(board.id, boards_manager.my_boards)
        self.assertNotIn(board.id, boards_manager.archived_boards)

        helpers.set_context(user2)
        boards_manager.load_user_boards()
        self.assertNotIn(board.id, boards_manager.last_modified_boards)
        self.assertIn(board.id, boards_manager.guest_boards)
        self.assertNotIn(board.id, boards_manager.my_boards)
        self.assertNotIn(board.id, boards_manager.archived_boards)

        column = board.create_column(1, u'test')
        column.create_card(u'test')
        boards_manager.load_user_boards()
        self.assertIn(board.id, boards_manager.last_modified_boards)

        board.archive()
        boards_manager.load_user_boards()
        self.assertIn(board.id, boards_manager.archived_boards)
