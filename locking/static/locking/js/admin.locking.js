/*
Client side handling of locking for the ModelAdmin change page.

Only works on change-form pages, not for inline edits in the list view.
*/

// Set the namespace.
var DJANGO_LOCKING = DJANGO_LOCKING || {};

// Make sure jQuery is available.
(function($) {


    if (typeof $.fn.hasClasses === 'undefined') {
        var re_classNameWhitespace = /[\n\t\r ]+/g;

        $.fn.hasClasses = function(classes) {
            if (!classes || typeof(classes) != 'object' || !classes.length) {
                return false;
            }
            var i = 0,
                l = this.length,
                classNameRegex = new RegExp("(" + classes.join(" | ") + ")");
            for (; i < l; i++) {
                if (this[i].nodeType !== 1) {
                    continue;
                }
                var className = this[i].className;
                var testStr = (" " + this[i].className + " ").replace(re_classNameWhitespace, " ");
                if (classNameRegex.test(testStr)) {
                    return true;
                }
            }
            return false;
        };
    }

    // Global error function that redirects to the frontpage if something bad
    // happens.
    DJANGO_LOCKING.error = function() {
        return;
        var text = ('An unexpected locking error occured. You will be' +
            ' forwarded to a safe place. Sorry!'
        );
        // Catch if gettext has not been included.
        try {
            alert(gettext(text));
        } catch(err) {
            alert(text);
        }
        window.location = '/';
    };

    var getUrl = function(action, id) {
        if (action != 'lock' && action != 'unlock' && action != 'lock_status') {
            return null;
        }
        var baseUrl = DJANGO_LOCKING.config.urls[action];
        if (typeof baseUrl == 'undefined') {
            return null;
        }
        var regex = new RegExp("\/0\/" + action + "\/$");
        return baseUrl.replace(regex, "/" + id + "/" + action + "/");
    };

    function unlock_click_event() {
        //Locking toggle function
        $("a.locking-status").click(function(e) {
            e.preventDefault();
            if (!$this.hasClass('locking-locked')) {
                return;
            }
            var $this = $(this);
            var user = $this.attr('data-locked-by');
            var lockId = $this.attr('data-lock-id');
            var unlockUrl = getUrl("unlock", lockId);
            if (unlockUrl) {
                if (confirm("User '" + user + "' is currently editing this " +
                            "content. Proceed with removing the lock?")) {
                    $.ajax({
                        url: unlockUrl,
                        async: false,
                        success: function() {
                            $this.hide();
                        }
                    });
                }
            }
        });
    }

    // Handles locking on the contrib.admin edit page.
    DJANGO_LOCKING.admin = function() {
        unlock_click_event();
        
        // Don't lock page if not on change-form page.
        if (!($("body").hasClass("change-form"))) return;

        if (typeof DJANGO_LOCKING.config != 'object') {
            return;
        }
        var urls = DJANGO_LOCKING.config.urls;

        if (typeof urls != 'object' || !urls['lock']) {
            return;
        }
        if (urls['lock'].match(/\/0\/lock\/$/)) {
            return;
        }

        // Texts.
        var text = {
            warn: gettext('Your lock on this page expires in less than %s' +
                ' minutes. Press save or <a href=".">reload the page</a>.'),
            is_locked: gettext('This page is locked by <em>%(for_user)s' +
                '</em> and editing is disabled.'),
            has_expired: gettext('Your lock on this page is expired!' +
                ' If you save now, your attempts may be thwarted due to another lock,' +
                ' or even worse, you may have stale data.'
            ),
            prompt_to_save: 'Do you wish to save the page?',
        };
        
        // Creates empty div in top of page.
        var create_notification_area = function() {
            $("#content-inner, #content").prepend(
                '<div id="locking_notification"></div>');
        };
        
        // Scrolls to the top, updates content of notification area and fades
        // it in.
        var update_notification_area = function(content, func) {
            $('html, body').scrollTop(0);
            $("#locking_notification").html(content).hide()
                                      .fadeIn('slow', func);
        };
        
        // Displays notice on top of page that the page is locked by someone
        // else.
        var display_islocked = function(data) {
            update_notification_area(interpolate(text.is_locked, data, true));
        };

        $(document).on('click', 'a', function(evt) {
            $a = $(this);

            var isDisabled = $("form").eq(0).data('isLockingDisabled');
            if (!isDisabled) {
                return true;
            }

            var isHandler = ($a.hasClasses([
                'grp-add-handler', 'add-handler',
                'add-another',
                'grp-delete-handler', 'delete-handler',
                'delete-link',
                'remove-handler', 'grp-remove-handler',
                'arrow-up-handler', 'grp-arrow-up-handler',
                'arrow-down-handler', 'grp-arrow-down-handler'
            ]));

            if (isHandler) {
                evt.stopPropagation();
                evt.preventDefault();
                alert("Page is locked");
            }
        });

        var toggle_ckeditor_readonly = function(isReadOnly) {
            var toggle_editor_readonly = function(editor) {
                if (editor.status == 'ready' || editor.status == 'basic_ready') {
                    editor.setReadOnly(isReadOnly);
                } else {
                    editor.on('contentDom', function(e) {
                        e.editor.setReadOnly(isReadOnly);
                    });
                }
            };
            if (window.CKEDITOR !== undefined) {
                switch (CKEDITOR.status) {
                    case 'basic_ready':
                    case 'ready':
                    case 'loaded':
                    case 'basic_loaded':
                        for (var instanceId in CKEDITOR.instances) {
                            toggle_editor_readonly(CKEDITOR.instances[instanceId]);
                        }
                        break;
                    default:
                        CKEDITOR.on("instanceReady", function(e) {
                            toggle_editor_readonly(e.editor);
                        });
                        break;
                }
            }
        };

        // Disables all form elements.
        var disable_form = function() {
            var $form = $("form").eq(0);
            var isDisabled = $form.data('isLockingDisabled');
            if (isDisabled) {
                return;
            }
            $form.data('isLockingDisabled', true);
            $(":input[disabled]").addClass('_locking_initially_disabled');
            $(":input:not(.django-select2, .django-ckeditor-textarea)").attr("disabled", "disabled");

            toggle_ckeditor_readonly(true);

            if (typeof $.fn.select2 === "function") {
                $('.django-select2').select2("disable");
            }
        };
        
        // Enables all form elements that was not disabled from the start.
        var enable_form = function() {
            var $form = $("form").eq(0);
            var isDisabled = $form.data('isLockingDisabled');
            if (!isDisabled) {
                return;
            }
            $form.data('isLockingDisabled', false);
            $(":input:not(.django-select2, .django-ckeditor-textarea)").not('._locking_initially_disabled').removeAttr("disabled");

            toggle_ckeditor_readonly(false);

            // Handle django-select2.  We really should add events to
            // django-locking so other items can know when to enable/disable
            if (typeof $.fn.select2 === "function") {
                $('.django-select2').select2("enable");
            }
        };
        
        // The user did not save in time, expire the page.
        var expire_page = function() {
            update_notification_area(text.has_expired);
        };


        var lock_renewer; // This needs to live in higher state so other functions can clear it.
        var setup_locked_page = function() {

            // Keep locked
            lock_renewer = setInterval(refresh_lock, 30000);
            
            // Disable lock when you leave
            $(window).unload(function() {
                // We have to assure that our unlock request actually
                // gets through before the user leaves the page, so it
                // shouldn't run asynchronously.
                if (!urls.unlock) {
                    return;
                }
                $.ajax({
                    url: urls.unlock,
                    async: false,
                    cache: false
                });
            });

        };
        
        // Request a lock on the page, and unlocks page when the user leaves.
        // Adds delayed execution of user notifications.
        var lock_page = function() {
            if (!urls.lock) {
                return;
            }
            $.ajax({
                url: urls.lock,
                cache: false,
                complete: function(jqXHR, textStatus) {
                    if (jqXHR.status === 403) {
                        disable_form();
                        display_islocked();
                    } else if (jqXHR.status === 200) {
                        enable_form();
                        setup_locked_page();
                    } else {
                        DJANGO_LOCKING.error();
                    }
                }
            });
        };

        var refresh_lock = function() {
            if (!urls.lock_status) {
                return;
            }
            $.getJSON(urls.lock_status, function(resp) {
                if (resp.for_user === DJANGO_GLOBALS.username) {
                    $.get(urls.lock);
                } else {
                    var msg; // If possible, we should let the user know who's competing for the lock.
                    if (resp.for_user || false) {
                        msg = resp.for_user + " removed your lock on this story.";
                    } else {
                        msg = "You lost your lock on this story. Save your work.";
                    }
                    alert(msg); // This should be obnoxious and grab focus.
                    expire_page();
                    clearInterval(lock_renewer); // Stop making calls, we're done.
                }
            });
        };
        
        // Polls server for the page lock status.
        var request_locking_info = function() {
            if (!urls.lock) {
                return;
            }
            $.ajax({
                url: urls.lock,
                success: function(data, textStatus, jqXHR) {
                    // The server gave us locking info. Either lock or keep it
                    // unlocked while showing notification.
                    if (!data.applies) {
                        // lock_page();
                        enable_form();
                        setup_locked_page();
                    } else {
                        disable_form();
                        display_islocked(data);
                    }
                },
                error: function(jqXHR, textStatus, errorThrown) {
                    if (jqXHR.status === 403) {
                        var data;
                        try {
                            data = $.parseJSON(jqXHR.responseText);
                        } catch(e) {}
                        disable_form();
                        display_islocked(data);
                    } else if (jqXHR.status === 200) {
                        enable_form();
                        setup_locked_page();
                    } else {
                        DJANGO_LOCKING.error();
                    }
                    
                },
                // DJANGO_LOCKING.error,
                cache: false
            });
        };
        
        // Initialize.
        create_notification_area();
        request_locking_info();

    };

    // Catches any error and redirects to a safe place if any.
    try {
        $(DJANGO_LOCKING.admin);
    } catch(err) {
        DJANGO_LOCKING.error();
    }

})((typeof grp == 'object' && grp.jQuery)
        ? grp.jQuery
        : (typeof django == 'object' && django.jQuery) ? django.jQuery : jQuery);
