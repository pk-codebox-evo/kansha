# -*- coding:utf-8 -*-
#--
# Copyright (c) 2012-2014 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
#--

from nagare import component, presentation, ajax, var, security
from nagare.i18n import _

from kansha.toolbox import overlay

from .comp import Label, CardLabels


def html_hex_to_rgb_tuple(hex_str):
    return tuple(ord(c) for c in hex_str.replace('#', '').decode('hex'))


def color_style(self):
    return 'background-color:%s' % self.data.color


@presentation.render_for(Label)
def render_Label(self, h, comp, *args):
    """Render the label as a simple colored block (text in it)"""
    with h.span(class_='card-label', style=color_style(self)):
        h << h.span(self.data.title)
    return h.root


@presentation.render_for(Label, model='color')
def render_Label_color(self, h, comp, *args):
    """Render the label as a simple colored block"""
    return h.span(class_='card-label', style=color_style(self), title=self.get_title())


@presentation.render_for(Label, model='inactive')
def render_Label_inactive(self, h, comp, *args):
    """Render the label as a simple colored block"""
    return h.span(class_='card-label', style='background-color: grey', title=self.get_title())


@presentation.render_for(Label, model='edit-color')
def render_Label_edit_color(self, h, comp, *args):
    """Edit the label color"""
    # If label changed reload columns
    if self._changed():
        h << h.script('reload_columns()')
        self._changed(False)
    h << component.Component(overlay.Overlay(lambda r: comp.render(r, model='color'),
                                             lambda r: comp.render(r,
                                                                   model='edit-color-overlay'),
                                             dynamic=False,
                                             title=_('Change color')))

    return h.root


@presentation.render_for(Label, model='edit-color-overlay')
def render_Label_edit_color_overlay(self, h, comp, *args):
    """Color chooser contained in the overlay body"""
    v = var.Var(self.data.color)
    i = h.generate_id()
    h << h.div(id=i, class_='label-color-picker clearfix')
    with h.form:
        h << h.input(type='hidden', value=v(), id='%s-hex-value' % i).action(v)
        h << h.button(_('Save'), class_='btn btn-primary').action(
            ajax.Update(action=lambda v=v: self.set_color(v())))
        h << ' '
        h << h.button(_('Cancel'), class_='btn').action(lambda: None)
    h << h.script("YAHOO.kansha.app.addColorPicker(%s)" % ajax.py2js(i))
    return h.root


@presentation.render_for(CardLabels, model='header')
def render_CardLabels_header(self, h, comp, *args):
    """Show labels inline (used in card summary view)"""
    if self.colors:
        with h.div(class_='inline-labels'):
            h << (component.Component(d, model='color')
                  for d in self.labels)
    return h.root


@presentation.render_for(CardLabels, model='list')
def render_CardLabels_list(self, h, comp, *args):
    """Show labels inline with grey label (for card edit view)"""
    h << h.script('YAHOO.kansha.app.hideOverlay();')
    with h.span(class_='inline-labels'):
        for label in self.get_available_labels():
            model = 'color' if label in self.labels else 'inactive'
            h << component.Component(Label(label), model)
    return h.root


@presentation.render_for(CardLabels)
def render_CardLabels(self, h, comp, *args):
    """Add or remove labels to card"""
    if security.has_permissions('edit', self.card):
        h << self.overlay
    else:
        h << comp.render(h, model="list")
    return h.root


@presentation.render_for(CardLabels, model='overlay')
def render_CardLabels_overlay(self, h, comp, *args):
    """Label chooser contained in the overlay's body"""
    with h.ul(class_='unstyled inline-labels'):
        for _i, label in enumerate(self.get_available_labels(), 1):
            with h.li:
                cls = ['card-label-choose']
                if label in self.labels:
                    cls.append('active')
                # Update the list of labels
                action1 = ajax.Update(
                    action=lambda label=label: self.activate(label))
                # Refresh the list
                action2 = ajax.Update(render=lambda r: comp.render(r, model='list'),
                                      component_to_update='list' + self.comp_id)
                with h.a(title=label.get_color(), class_=' '.join(cls),).action(ajax.Updates(action1, action2)):
                    h << h.span(class_="card-label",
                                style='background-color: %s' % label.get_color())
                    h << h.span(label.get_title())
    return h.root
