from datetime import datetime
import uuid

from pyramid.view import view_config, view_defaults, forbidden_view_config
from pyramid.httpexceptions import HTTPFound, HTTPForbidden
from pyramid.response import Response
from pyramid.security import remember, forget

from deform import Form, Button, ValidationFailure
from authomatic.adapters import WebObAdapter

from phoenix.security import Admin, Guest, authomatic
from phoenix.security import allowed_auth_protocols
from phoenix.security import AUTH_PROTOCOLS
from phoenix.twitcherclient import generate_access_token

import logging
LOGGER = logging.getLogger("PHOENIX")


def add_user(request, login_id, email='', openid='', name='unknown', organisation='', notes='', group=Guest):
    user = dict(
        identifier=str(uuid.uuid1()),
        login_id=login_id,
        email=email,
        openid=openid,
        name=name,
        organisation=organisation,
        notes=notes,
        group=group,
        creation_time=datetime.now(),
        last_login=datetime.now())
    request.db.users.save(user)
    return request.db.users.find_one({'identifier': user['identifier']})


@forbidden_view_config(renderer='templates/account/forbidden.pt', layout="default")
def forbidden(request):
    request.response.status = 403
    return dict()


@view_config(route_name='account_register', renderer='templates/account/register.pt',
             permission='view', layout="default")
def register(request):
    return dict()


@view_defaults(permission='view', layout='default')
class Account(object):
    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.collection = request.db.users

    def appstruct(self):
        return dict()

    def schema(self):
        return None

    def generate_form(self):
        btn = Button(name='submit', title='Sign In',
                     css_class="btn btn-success btn-lg btn-block")
        form = Form(schema=self.schema(), buttons=(btn,), formid='deform')
        return form

    def process_form(self, form):
        try:
            controls = self.request.POST.items()
            appstruct = form.validate(controls)
        except ValidationFailure, e:
            self.session.flash("<strong>Error:</strong> Validation failed %s".format(e.message), queue='danger')
            return dict(form=e.render())
        else:
            return self._handle_appstruct(appstruct)

    def _handle_appstruct(self, appstruct):
        raise NotImplementedError("Needs to be implemented in subclass")

    def send_notification(self, email, subject, message):
        """Sends email notification to admins.

        Sends email with the pyramid_mailer module.
        For configuration look at documentation http://pythonhosted.org//pyramid_mailer/
        """
        from pyramid_mailer import get_mailer
        mailer = get_mailer(self.request)

        sender = "noreply@%s" % (self.request.server_name)

        recipients = set()
        for user in self.collection.find({'group': Admin}):
            email = user.get('email')
            if email:
                recipients.add(email)

        if len(recipients) > 0:
            from pyramid_mailer.message import Message
            message = Message(subject=subject,
                              sender=sender,
                              recipients=recipients,
                              body=message)
            try:
                mailer.send_immediately(message, fail_silently=True)
            except:
                LOGGER.error("failed to send notification")
        else:
            LOGGER.warn("Can't send notification. No admin emails are available.")

    def login_success(self, login_id, email='', name="Unknown", openid=None, local=False):
        user = self.collection.find_one(dict(login_id=login_id))
        if user is None:
            LOGGER.warn("new user: %s", login_id)
            user = add_user(self.request, login_id=login_id, email=email, group=Guest)
            subject = 'Phoenix: New user %s logged in on %s' % (name, self.request.server_name)
            message = 'Please check the activation of the user {0} on the Phoenix host {1}'.format(
                name, self.request.server_name)
            self.send_notification(email, subject, message)
        if local and login_id == 'phoenix@localhost':
            user['group'] = Admin
        user['last_login'] = datetime.now()
        if openid:
            user['openid'] = openid
        user['name'] = name
        self.collection.update({'login_id': login_id}, user)
        self.session.flash("Hello <strong>{0}</strong>. Welcome to Phoenix.".format(name), queue='info')
        if user.get('group') == Guest:
            msg = """
            You are member of the <strong>Guest</strong> group.
            You are allowed to submit processes without <strong>access restrictions</strong>.
            """
            self.session.flash(msg, queue='info')
        else:
            generate_access_token(self.request.registry, userid=user['identifier'])
        headers = remember(self.request, user['identifier'])
        return HTTPFound(location=self.request.route_path('home'), headers=headers)

    def login_failure(self, message=None):
        msg = 'Sorry, login failed.'
        if message:
            msg = 'Sorry, login failed: {0}'.format(message)
        self.session.flash(msg, queue='danger')
        return HTTPFound(location=self.request.route_path('home'))

    @view_config(route_name='account_login', renderer='templates/account/login.pt')
    def login(self):
        protocol = self.request.matchdict.get('protocol', 'phoenix')
        allowed_protocols = allowed_auth_protocols(self.request)

        # Make sure disabled protocols are not accessed directly
        if protocol not in allowed_protocols:
            return HTTPForbidden()

        form = self.generate_form(protocol)
        if 'submit' in self.request.POST:
            return self.process_form(form, protocol)
        # TODO: Add ldap to title?
        return dict(form=form.render(self.appstruct()))

    @view_config(route_name='account_logout', permission='edit')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('home'), headers=headers)

    @view_config(route_name='account_auth')
    def authomatic_login(self):
        _authomatic = authomatic(self.request)

        provider_name = self.request.matchdict.get('provider_name')

        # Start the login procedure.
        response = Response()
        result = _authomatic.login(WebObAdapter(self.request, response), provider_name)

        if result:
            if result.error:
                # Login procedure finished with an error.
                return self.login_failure(message=result.error.message)
            elif result.user:
                if not (result.user.name and result.user.id):
                    result.user.update()
                # Hooray, we have the user!
                LOGGER.info("login successful for user %s", result.user.name)
                if result.provider.name in ['dkrz', 'ipsl', 'smhi', 'badc', 'pcmdi']:
                    # TODO: change login_id ... more infos ...
                    return self.login_success(login_id=result.user.id,
                                              email=result.user.email,
                                              openid=result.user.id,
                                              name=result.user.name)
                elif result.provider.name == 'github':
                    # TODO: fix email ... get more infos ... which login_id?
                    login_id = "{0.username}@github.com".format(result.user)
                    #email = "{0.username}@github.com".format(result.user)
                    # get extra info
                    if result.user.credentials:
                        pass
                    return self.login_success(login_id=login_id, name=result.user.name)
        return response
