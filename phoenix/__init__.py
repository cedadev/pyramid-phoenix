import os

import logging
logger = logging.getLogger(__name__)

__version__ = (0, 4, 5, 'final', 1)

def get_version():
    import phoenix.version
    return phoenix.version.get_version(__version__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from pyramid.config import Configurator
    from pyramid.events import subscriber
    from pyramid.events import NewRequest
    from pyramid.authentication import AuthTktAuthenticationPolicy
    from pyramid.authorization import ACLAuthorizationPolicy
    from pyramid.settings import asbool
    from phoenix.security import groupfinder, root_factory

    # security
    # TODO: move to security
    authn_policy = AuthTktAuthenticationPolicy(
        settings.get('authomatic.secret'), callback=groupfinder, hashalg='sha512')
    authz_policy = ACLAuthorizationPolicy()
    config = Configurator(root_factory=root_factory, settings=settings)
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    # beaker session
    config.include('pyramid_beaker')

    # chameleon templates
    config.include('pyramid_chameleon')
    
    # deform
    #config.include('pyramid_deform')
    #config.include('js.deform')

    # mailer
    config.include('pyramid_mailer')

    # celery
    config.include('pyramid_celery')
    config.configure_celery(global_config['__file__'])

    # ldap
    config.include('pyramid_ldap')
    # FK: Ldap setup functions will be called on demand.

    # static views (stylesheets etc)
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_static_view('deform_static', 'deform:static', cache_max_age=3600)

    # routes 
    config.add_route('home', '/')
    config.add_route('download', 'download/{filename:.*}')

    # login
    config.add_route('account_login', '/account/login/{protocol}')
    config.add_route('account_logout', '/account/logout')
    config.add_route('account_auth', '/account/auth/{provider_name}')
    config.add_route('account_register', '/account/register')

    # dashboard
    config.include('phoenix.dashboard')
    
    # processes
    config.include('phoenix.processes')

    # job monitor
    config.include('phoenix.monitor')

    # user profile
    config.include('phoenix.profile')

    # settings
    config.include('phoenix.settings')

    # supervisor
    config.include('phoenix.supervisor')

    # services
    config.include('phoenix.services')

    # solr
    config.add_route('index_service', '/solr/{service_id}/index')
    config.add_route('clear_index', '/solr/clear')
    
    # wizard
    config.include('phoenix.wizard')

    # readthedocs
    config.add_route('readthedocs', 'https://pyramid-phoenix.readthedocs.org/en/latest/{part}.html')

    # A quick access to the login button
    from phoenix.utils import button
    config.add_request_method(button, 'login_button', reify=True)

    # check if solr is activated
    def solr_activated(request):
        settings = request.registry.settings
        return asbool(settings.get('phoenix.solr', True))
    config.add_request_method(solr_activated, reify=True)

    # check if wms is activated
    def wms_activated(request):
        settings = request.registry.settings
        return asbool(settings.get('phoenix.wms', True))
    config.add_request_method(wms_activated, reify=True)

    # check if flower is activated
    def flower_activated(request):
        settings = request.registry.settings
        return asbool(settings.get('phoenix.flower', True))
    config.add_request_method(flower_activated, reify=True)

    # check if csw is activated
    def csw_activated(request):
        settings = request.registry.settings
        return asbool(settings.get('phoenix.csw', True))
    config.add_request_method(csw_activated, reify=True)

    # max file size for upload in MB
    def max_file_size(request):
        settings = request.registry.settings
        return int(settings.get('phoenix.max_file_size', '200'))
    config.add_request_method(max_file_size, reify=True)

    # use json_adapter for datetime
    # http://docs.pylonsproject.org/projects/pyramid/en/1.5-branch/narr/renderers.html#json-renderer
    from pyramid.renderers import JSON
    import datetime
    json_renderer = JSON()
    def datetime_adapter(obj, request):
        return obj.isoformat()
    json_renderer.add_adapter(datetime.datetime, datetime_adapter)
    import bson
    def objectid_adapter(obj, request):
        return str(obj)
    json_renderer.add_adapter(bson.objectid.ObjectId, objectid_adapter)
    ## def wpsexception_adapter(obj, request):
    ##     logger.debug("mongo adapter wpsexception called")
    ##     return '%s %s: %s' % (obj.code, obj.locator, obj.text)
    ## from owslib import wps
    ## json_renderer.add_adapter(wps.WPSException, wpsexception_adapter)
    config.add_renderer('json', json_renderer)

    # MongoDB
    # TODO: maybe move this to models.py?
    #@subscriber(NewRequest)
    def add_mongodb(event):
        settings = event.request.registry.settings
        if settings.get('db') is None:
            try:
                from phoenix.models import mongodb
                settings['db'] = mongodb(event.request.registry)
            except:
                logger.exception('Could not connect to mongodb')
        event.request.db = settings.get('db')
    config.add_subscriber(add_mongodb, NewRequest)
    
    # malleefowl wps
    if asbool(settings.get('phoenix.wizard', True)):
        def add_wps(event):
            settings = event.request.registry.settings
            if settings.get('wps') is None:
                try:
                    from owslib.wps import WebProcessingService
                    settings['wps'] = WebProcessingService(url=settings['wps.url'])
                except:
                    logger.exception('Could not connect malleefowl wps %s', settings['wps.url'])
            event.request.wps = settings.get('wps')
        config.add_subscriber(add_wps, NewRequest)
        
    # catalog service
    if asbool(settings.get('phoenix.csw', True)):
        def add_csw(event):
            settings = event.request.registry.settings
            if settings.get('csw') is None:
                try:
                    from owslib.csw import CatalogueServiceWeb
                    settings['csw'] = CatalogueServiceWeb(url=settings['csw.url'])
                except:
                    logger.exception('Could not connect catalog service %s', settings['csw.url'])
            event.request.csw = settings.get('csw')
        config.add_subscriber(add_csw, NewRequest)
    
    config.scan('phoenix')

    return config.make_wsgi_app()

