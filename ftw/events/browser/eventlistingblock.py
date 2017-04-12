from Acquisition._Acquisition import aq_inner, aq_parent
from ftw.events import _
from ftw.events import utils
from ftw.events.interfaces import IEventPage
from ftw.simplelayout.browser.blocks.base import BaseBlock
from ftw.simplelayout.contenttypes.behaviors import IHiddenBlock
from plone import api
from plone.app.event.base import _prepare_range, filter_and_resort
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.component import getMultiAdapter
from zope.contentprovider.interfaces import IContentProvider
from zope.i18n import translate
import datetime


class EventListingBlockView(BaseBlock):
    template = ViewPageTemplateFile('templates/eventlistingblock.pt')

    def get_block_info(self):
        """
        This method returns a dict containing information to be used in
        the block's template.
        """
        more_items_link_url = ''
        if self.context.show_more_items_link:
            more_items_link_url = '/'.join([self.context.absolute_url(), 'events'])

        more_items_link_label = (
            self.context.more_items_link_label or
            translate(_('more_items_link_label', default=u'More Items'),
                      context=self.request)
        )

        info = {
            'title': self.context.title,
            'show_title': self.context.show_title,
            'more_items_link_url': more_items_link_url,
            'more_items_link_label': more_items_link_label,
            'hide_empty_block':  self.context.hide_empty_block,
        }

        return info

    def get_items(self):
        """
        Returns a list of dicts where each dict contains the data of an
        event page. It is called from the template.
        """
        catalog = getToolByName(self.context, 'portal_catalog')

        start = None
        end = None

        if self.context.exclude_past_events:
            # Start from midnight of today. This way the query will also include
            # events which have ended just a few hours ago.
            midnight_of_today = datetime.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            start = midnight_of_today

        # Inspired by `plone.app.event.base.get_events`.
        start, end = _prepare_range(self.context, start, end)

        brains = catalog.searchResults(
            **self.get_query(start, end)
        )

        # Inspired by `plone.app.event.base.get_events`.
        brains = filter_and_resort(
            context=self.context, brains=brains, start=start,
            end=end, sort='start', sort_reverse=False
        )

        if self.context.quantity:
            brains = brains[:self.context.quantity]

        items = [self.get_event_page_dict(brain) for brain in brains]

        return items

    def get_query(self, start=None, end=None):
        query = {
            'object_provides': IEventPage.__identifier__,
            'sort_on': 'start',
        }

        # Inspired by `plone.app.event.base.get_events`.
        if start:
            # All events from start date ongoing:
            # The minimum end date of events is the date from which we search.
            query['end'] = {'query': start, 'range': 'min'}
        if end:
            # All events until end date:
            # The maximum start date must be the date until we search.
            query['start'] = {'query': end, 'range': 'max'}

        parent = aq_parent(aq_inner(self.context))
        if self.context.current_context:
            # `parent` is the object containing this block.
            path = '/'.join(parent.getPhysicalPath())
            query['path'] = {'query': path}

        elif self.context.filter_by_path:
            portal_path = '/'.join(api.portal.get().getPhysicalPath())
            paths = ['/'.join([portal_path, path])
                     for path in self.context.filter_by_path]
            query['path'] = {'query': paths}

        if self.context.subjects:
            query['Subject'] = self.context.subjects

        # Show inactive events if the current user is allowed to add events on the
        # parent of the event listing block. We must only render the inactive events
        # if the block renders events from its parent (in order not to allow the user
        # to view news items he is not allowed to see).
        if self.context.current_context \
                and not self.context.filter_by_path \
                and api.user.has_permission('ftw.events: Add Event Page', obj=parent):
            query['show_inactive'] = True

        return query

    def get_event_page_dict(self, brain):
        """
        Constructs a dict containing the data of the brain of an event page.
        """
        obj = brain.getObject()

        description = ''
        if self.context.show_description:
            description = brain.Description
        if self.context.description_length:
            description = utils.crop_text(
                description, self.context.description_length
            )

        # Copied from "plone.app.event.portlets.portlet_events.Renderer#formatted_date".
        provider = getMultiAdapter(
            (self.context, self.request, self),
            IContentProvider, name='formatted_date'
        )
        date_snippet = provider(obj)

        item = {
            'title': brain.Title,
            'description': description,
            'url': brain.getURL(),
            'brain': brain,
            'date_snippet': date_snippet,
            'location': obj.location or '',
        }
        return item


from ftw.sliderblock.browser.sliderblock import SliderBlockView
from ftw.simplelayout.browser.actions import DefaultActions
from collections import OrderedDict
import json


class SliderView(SliderBlockView, EventListingBlockView):
    template = ViewPageTemplateFile('templates/eventslider.pt')

    def panes(self):
        return self.get_items()

    def get_slick_config(self):
        # The config value may contain unwanted new lines. Let's remove them
        # by loading and dumping as json.
        config = json.loads('{"autoplay": false, "dots": true, "adaptiveHeight": true}')
        config = self.extend_translations(config)
        return json.dumps(config)

    def get_template_data(self):
        data = []
        for item in self.panes():
            event = item['brain'].getObject()
    
            # Copied from "plone.app.event.portlets.portlet_events.Renderer#formatted_date".
            provider = getMultiAdapter(
                (self.context, self.request, self),
                IContentProvider, name='formatted_date'
            )
            date_snippet = provider(event)

            data.append({
                'uid': event.UID(),
                'title': event.title,
                # 'show_title': event.show_title,
                'show_title': True,
                'title_css_classes': 'eventTitle',
                'text': event.Description(),
                # 'show_event_caption': event.show_title or event.text,
                'show_event_caption': True,
                'image_tag': self.get_image_tag(event),
                'link_url': event.absolute_url(),
                'date': date_snippet
            })
        return data

    def get_image_tag(self, event):
        view = event.restrictedTraverse('@@leadimage')
        if view.has_image:
            scaler = view.block.restrictedTraverse('@@images')
            return scaler.scale('image', scale='sliderblock', direction="thumbnail").tag()
        else:
            return ''

class EventlistingBlockActions(DefaultActions):

    def specific_actions(self):
        actions = super(EventlistingBlockActions, self).specific_actions().items()

        view_actions = [
            ('defaultview', {
                'class': 'icon-default-view server-action',
                'title': translate(
                    _(u'label_default_view', default=u'Standard Ansicht'),
                    context=self.request),
                'href': './sl-ajax-reload-block-view',
                'data-view_name': 'block_view',
            }),
            ('teaserview', {
                'class': 'icon-teaser-view server-action',
                'title': translate(
                    _(u'label_teaser_view',
                      default=u'Teaser Block Ansicht'),
                    context=self.request),
                'href': './sl-ajax-reload-block-view',
                'data-view_name': 'slider_view',
            })
        ]

        return OrderedDict(actions + view_actions)
