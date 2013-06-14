import re
import functools
import json

try:
    from custom_admin import admin
except ImportError:
    from django.contrib import admin

from django.core.urlresolvers import reverse
from django.utils import html as html_utils
from django.utils.functional import curry
from django.utils.safestring import mark_safe
from django.utils.timesince import timeuntil
from django.utils.translation import ugettext as _
from django.contrib.admin.util import flatten_fieldsets

from .models import Lock
from .forms import locking_form_factory
from . import settings as locking_settings, views as locking_views


json_encode = json.JSONEncoder(indent=4).encode


class LockableAdminMixin(object):

    @property
    def media(self):
        opts = self.model._meta
        info = (opts.app_label, opts.module_name)

        media = super(LockableAdminMixin, self).media
        media.add_js((
            locking_settings.STATIC_URL + 'locking/js/jquery.url.packed.js',
            # We call admin:%(app_label)s_%(model)s_lock_js with 0 (the pk)
            # with the intention of doing a string replace on the url in
            # render_change_form(), where we know what the primary key is.
            #
            # This is hacky, but necessary since the add_view does not have a
            # primary key, given that the object has not yet been saved.
            reverse('admin:%s_%s_lock_js' % info, args=[0]),
            locking_settings.STATIC_URL + "locking/js/admin.locking.js?v=5"
        ))
        media.add_css({
            "all": (locking_settings.STATIC_URL + 'locking/css/locking.css',)
        })
        return media

    def get_urls(self):
        """
        Appends locking urls to the ModelAdmin's own urls. Its url names
        are patterned after the urls for the ModelAdmin's views (e.g.
        changelist_view, change_view).

        The url names appended are:

            admin:%(app_label)s_%(object_name)s_lock
            admin:%(app_label)s_%(object_name)s_unlock
            admin:%(app_label)s_%(object_name)s_lock_status
            admin:%(app_label)s_%(object_name)s_lock_js
        """
        try:
            from django.conf.urls.defaults import patterns, url
        except ImportError:
            from django.conf.urls import patterns, url

        def wrap(view):
            curried_view = curry(view, self)
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(curried_view)(*args, **kwargs)
            return functools.update_wrapper(wrapper, view)

        opts = self.model._meta
        info = (opts.app_label, opts.module_name)

        urlpatterns = patterns('',
            url(r'^(.+)/locking_variables\.js',
                wrap(locking_views.locking_js),
                name="%s_%s_lock_js" % info),
            url(r'^(.+)/lock/$',
                wrap(locking_views.lock),
                name="%s_%s_lock" % info),
            url(r'^(.+)/unlock/$',
                wrap(locking_views.unlock),
                name="%s_%s_unlock" % info),
            url(r'^(.+)/lock_status/$',
                wrap(locking_views.lock_status),
                name="%s_%s_lock_status" % info))
        urlpatterns += super(LockableAdminMixin, self).get_urls()
        return urlpatterns

    def render_change_form(self, request, context, add=False, obj=None, **kwargs):
        obj_pk = getattr(obj, 'pk', None)
        if not add and obj_pk:
            media = context.pop('media', None)
            if media:
                # This is our hacky string-replacement, described more fully
                # in the comments for the `media` @property
                media = re.sub(r'/0/(locking_variables\.js)', r'/%d/\1' % obj_pk, unicode(media))
                context['media'] = mark_safe(media)
        return super(LockableAdminMixin, self).render_change_form(
                request, context, add=add, obj=obj, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """
        Returns a Form class for use in the admin add view. This is used by
        add_view and change_view.
        """
        if self.declared_fieldsets:
            fields = flatten_fieldsets(self.declared_fieldsets)
        else:
            fields = None
        if self.exclude is None:
            exclude = []
        else:
            exclude = list(self.exclude)
        exclude.extend(kwargs.get("exclude", []))
        exclude.extend(self.get_readonly_fields(request, obj))
        # if exclude is an empty list we pass None to be consistant with the
        # default on modelform_factory
        exclude = exclude or None
        defaults = {
            "form": self.form,
            "fields": fields,
            "exclude": exclude,
            "formfield_callback": curry(self.formfield_for_dbfield, request=request),
            "request": request,
        }
        defaults.update(kwargs)
        return locking_form_factory(self.model, **defaults)

    def save_model(self, request, obj, *args, **kwargs):
        """
        Clears the lock owned by the current user, if it wasn't cleared on
        unload, then saves the admin model instance.
        """
        if getattr(obj, 'pk', None):
            try:
                lock = Lock.objects.get_lock_for_object(obj)
            except Lock.DoesNotExist:
                pass
            else:
                if lock.is_locked and lock.is_locked_by(request.user):
                    lock.unlock_for(request.user)
        super(LockableAdminMixin, self).save_model(request, obj, *args, **kwargs)

    def queryset(self, request):
        """
        Extended queryset method which adds a custom SQL select column,
        `_locking_user_pk`, which is set to the pk of the current request's
        user instance. Doing this allows us to access the user id by
        obj._locking_user_pk for any object returned from this queryset.
        """
        qs = super(LockableAdminMixin, self).queryset(request)
        return qs.extra(select={
            '_locking_user_pk': "%d" % request.user.pk,
        })

    def get_lock_for_admin(self, obj):
        """
        Returns the locking status along with a nice icon for the admin
        interface use in admin list display like so:
        list_display = ['title', 'get_lock_for_admin']
        """
        current_user_id = obj._locking_user_pk

        try:
            lock = Lock.objects.get_lock_for_object(obj)
        except Lock.DoesNotExist:
            return u""
        else:
            if not lock.is_locked:
                return u""

        until = timeuntil(lock.lock_expiration_time)

        locked_by_fullname = lock.locked_by.get_full_name()

        if lock.locked_by.pk == current_user_id:
            msg = _(u"You own this lock for %s longer") %  until
            css_class = 'locking-edit'
        else:
            msg = _(u"Locked by %s for %s longer") % (until, locked_by_fullname)
            css_class = 'locking-locked'

        return (
            u'  <a href="#" title="%(msg)s"'
            u'     data-lock-id="%(lock_id)s"'
            u'     data-locked-by="%(fullname)s"'
            u'     class="locking-status %(css_class)s"></a>'
        ) % {
            'msg': html_utils.escape(msg),
            'lock_id': lock.pk,
            'fullname': html_utils.escape(locked_by_fullname),
            'css_class': css_class,}

    get_lock_for_admin.allow_tags = True
    get_lock_for_admin.short_description = 'Lock'



class LockableAdmin(LockableAdminMixin, admin.ModelAdmin):
    pass
