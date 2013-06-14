"""
These views are called from javascript to open and close assets (objects), in order
to prevent concurrent editing.
"""
import json
import textwrap

from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.contrib.contenttypes.models import ContentType

from .utils import timedelta_to_seconds
from .models import Lock, ObjectLockedError
from . import settings as locking_settings


json_encode = json.JSONEncoder(indent=4).encode


def lock(model_admin, request, object_id, extra_context=None):
    ct = ContentType.objects.get_for_model(model_admin.model)
    try:
        lock = Lock.objects.get(content_type=ct, object_id=object_id)
    except Lock.DoesNotExist:
        lock = Lock(content_type=ct, object_id=object_id)

    try:
        lock.lock_for(request.user)
    except ObjectLockedError:
        status = 403
    else:
        status = 200
        lock.save()
    return lock_status(model_admin, request, object_id,
            extra_context=extra_context, status=status)


def unlock(model_admin, request, object_id, extra_context=None):
    ct = ContentType.objects.get_for_model(model_admin.model)
    try:
        lock = Lock.objects.get(content_type=ct, object_id=object_id)
    except Lock.DoesNotExist:
        return HttpResponse(status=404)
    else:
        lock.delete()
        return HttpResponse(status=200)


def lock_status(model_admin, request, object_id, extra_context=None, **kwargs):
    data = {
        'is_active': False,
        'applies': False,
        'for_user': None,
    }
    ct = ContentType.objects.get_for_model(model_admin.model)
    try:
        lock = Lock.objects.get(content_type=ct, object_id=object_id)
    except Lock.DoesNotExist:
        pass
    else:
        data.update({
            'is_active': lock.is_locked,
            'for_user': getattr(lock.locked_by, 'username', None),
            'applies': lock.lock_applies_to(request.user),
        })
    status = kwargs.pop('status', 200)
    return HttpResponse(json_encode(data), mimetype='application/json', status=status)


def locking_js(model_admin, request, object_id, extra_context=None):
    opts = model_admin.model._meta
    info = (opts.app_label, opts.module_name)

    locking_urls = {
        "lock": reverse("admin:%s_%s_lock" % info, args=[object_id]),
        "unlock": reverse("admin:%s_%s_unlock" % info, args=[object_id]),
        "lock_status": reverse("admin:%s_%s_lock_status" % info,
            args=[object_id]),
    }

    js_vars = {
        'urls': locking_urls,
        'time_until_expiration': timedelta_to_seconds(
                locking_settings.TIME_UNTIL_EXPIRATION),
        'time_until_warning': timedelta_to_seconds(
                locking_settings.TIME_UNTIL_WARNING),
    }

    response_js = textwrap.dedent("""
        var DJANGO_LOCKING = (typeof window.DJANGO_LOCKING != 'undefined')
                           ? DJANGO_LOCKING : {{}};
        DJANGO_LOCKING.config = {config_data}
    """).strip().format(config_data=json_encode(js_vars))
    return HttpResponse(response_js, mimetype='application/x-javascript')
