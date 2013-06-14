from django import forms
from django.core.exceptions import NON_FIELD_ERRORS
from django.forms.models import ModelForm, modelform_factory
from django.utils.timesince import timeuntil

from locking.models import Lock


def locking_form_factory(model, form=ModelForm, *args, **kwargs):
    """
    Since we no longer decorate or extend models as part of locking, this is
    the most reliable way to throw ValidationErrors for hard locks in the
    admin.

    How it works:
        - We override ModelAdmin.get_form in locking.admin.LockableAdminMixin
          so that it uses this function instead of modelform_factory().
        - We create a new class, dynamically, which extends `form` (passed via
          kwarg) and which performs the validation check in _post_clean()
          after calling the super().
        - We pass the new form class in place of the original to
          modelform_factory().
    """

    request = kwargs.pop('request')
    user = getattr(request, 'user', None)

    class locking_form(form):

        def _post_clean(self):
            super(locking_form, self)._post_clean()
            # We were not passed a user, so we have no way of telling who is
            # the owner of an object's lock; better not to raise
            # ValidationError in that case
            if not user:
                return

            # If this model doesn't have primary keys, don't continue
            if not self._meta.model._meta.pk:
                return

            # If there are already errors, no point checking lock since save
            # will be prevented
            if self.errors:
                return

            # If we don't have a saved object yet, it could not have a lock
            if not self.instance.pk:
                return

            try:
                lock = Lock.objects.get_lock_for_object(self.instance)
            except Lock.DoesNotExist:
                return

            # If either of these conditions are met, we don't have an error.
            # If we pass beyond this point, we have a validation error because
            # the object is locked by a user other than the current user.
            if not lock.is_locked or lock.is_locked_by(user):
                return

            try:
                raise forms.ValidationError((
                    u"You cannot save this %(verbose_name)s because it is "
                    u"locked by %(user)s. The lock will expire in "
                    u"%(time_remaining)s if that user is idle.") % {
                        'verbose_name': self._meta.model._meta.verbose_name,
                        'user': lock.locked_by.get_full_name(),
                        'time_remaining': timeuntil(lock.lock_expiration_time),
                    })
            except forms.ValidationError as e:
                self._update_errors({NON_FIELD_ERRORS: e.messages})

    locking_form.__name__ = form.__name__
    return modelform_factory(model, form=locking_form, *args, **kwargs)
