# -*- coding:utf-8 -*-
#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare import component, presentation, security
from nagare.i18n import _

from .comp import Board

class TemplatesManager(object):
    def __init__(self, app_title, app_banner, theme, card_extensions, user, search_engine, services_service):
        self.app_banner = app_banner
        self.app_title = app_title
        self.theme = theme
        self.user_username = user.username
        self.user_source = user.source
        self.card_extensions = card_extensions
        self.search_engine = search_engine
        self._services = services_service
        self.templates = [template for template in self.get_templates()]

    def handle_action(self, answer):
        action, obj = answer[0], answer[1]
        if action == 'delete':
            obj.delete()
            self.templates = [template for template in self.get_templates()]

    def get_templates(self):
        if security.has_permissions('admin'):
            source = Board.get_all_templates()
        else:
            source = Board.get_my_templates_for(self.user_username, self.user_source)
        for template in source:
            template = self._services(Board,
                                      template.id,
                                      self.app_title,
                                      self.app_banner,
                                      self.theme,
                                      self.card_extensions,
                                      self.search_engine)
            yield component.Component(template, 'template_item')


@presentation.render_for(TemplatesManager)
def render_TemplatesManager(self, h, comp, model):
    h.head.css_url('css/themes/home.css')
    h.head.css_url('css/themes/%s/home.css' % self.theme)

    h << h.h1(_(u'Templates'))

    with h.ul(class_='board-labels'):
        h << [template.on_answer(self.handle_action) for template in self.templates]

    return h.root