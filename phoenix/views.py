# views.py
# Copyright (C) 2013 the ClimDaPs/Phoenix authors and contributors
# <see AUTHORS file>
#
# This module is part of ClimDaPs/Phoenix and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import os
import datetime

from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPException, HTTPFound, HTTPNotFound
from pyramid.response import Response
from pyramid.renderers import render
from pyramid.security import remember, forget, authenticated_userid
from pyramid.events import subscriber, BeforeRender
from pyramid_deform import FormView
from deform import Form
from deform.form import Button
from authomatic import Authomatic
from authomatic.adapters import WebObAdapter
import config_public as config

from owslib.csw import CatalogueServiceWeb
from owslib.wps import WebProcessingService, WPSExecution, ComplexData

from .security import is_valid_user

from .models import update_user

from .wps import WPSSchema  

from .helpers import wps_url
from .helpers import csw_url
from .helpers import supervisor_url
from .helpers import thredds_url
from .helpers import update_wps_url
from .helpers import execute_wps

import logging

log = logging.getLogger(__name__)

authomatic = Authomatic(config=config.config,
                        secret=config.SECRET,
                        report_errors=True,
                        logging_level=logging.DEBUG)

@subscriber(BeforeRender)
def add_global(event):
    event['message_type'] = 'alert-info'
    event['message'] = ''


# Exception view
# --------------

# @view_config(context=Exception)
# def error_view(exc, request):
#     msg = exc.args[0] if exc.args else ''
#     response = Response(str(msg))
#     response.status_int = 500
#     response.content_type = 'text/xml'
#     return response


# sign-in
# -------

@view_config(
    route_name='signin', 
    layout='default', 
    renderer='templates/signin.pt',
    permission='view')
def signin(request):
    log.debug("sign-in view")
    return dict()

# logout
# --------

@view_config(
    route_name='logout',
    permission='edit')
def logout(request):
    log.debug("logout")
    headers = forget(request)
    return HTTPFound(location = request.route_url('home'),
                     headers = headers)

# forbidden view
# --------------

@forbidden_view_config(
    renderer='templates/forbidden.pt',
    )
def forbidden(request):
    request.response.status = 403
    return dict(message=None)

# register view
# -------------
@view_config(
    route_name='register',
    renderer='templates/register.pt',
    permission='view')
def register(request):
    return dict(email=None)


# local login for admin and demo user
# -----------------------------------
@view_config(
    route_name='login_local',
    #check_csrf=True, 
    permission='view')
def login_local(request):
    log.debug("login with local account")
    password = request.params.get('password')
    # TODO: need some work work on local accounts
    if (False):
        email = "demo@climdaps.org"
        update_user(request, user_id=email)

        if is_valid_user(request, email):
            request.response.text = render('phoenix:templates/openid_success.pt',
                                           {'result': email},
                                           request=request)
            # Add the headers required to remember the user to the response
            request.response.headers.extend(remember(request, email))
        else:
            request.response.text = render('phoenix:templates/register.pt',
                                           {'email': email}, request=request)
    else:
        request.response.text = render('phoenix:templates/forbidden.pt',
                                       {'message': 'Wrong Password'},
                                       request=request)

    return request.response

# persona login
# -------------

@view_config(route_name='login', check_csrf=True, renderer='json', permission='view')
def login(request):
    # TODO: update login to my needs
    # https://pyramid_persona.readthedocs.org/en/latest/customization.html#do-extra-work-or-verification-at-login

    log.debug('login with persona')

    # Verify the assertion and get the email of the user
    from pyramid_persona.views import verify_login 
    email = verify_login(request)

    # update user list
    update_user(request, user_id=email)
    
    # check whitelist
    if not is_valid_user(request, email):
        log.info("persona login: user %s is not registered", email)
        update_user(request, user_id=email, activated=False)
        #    request.session.flash('Sorry, you are not on the list')
        return {'redirect': '/register', 'success': False}
    log.info("persona login successful for user %s", email)
    update_user(request, user_id=email, activated=True)
    # Add the headers required to remember the user to the response
    request.response.headers.extend(remember(request, email))
    # Return a json message containing the address or path to redirect to.
    #return {'redirect': request.POST['came_from'], 'success': True}
    return {'redirect': '/', 'success': True}

# authomatic openid login
# -----------------------

@view_config(
    route_name='login_openid',
    permission='view')
def login_openid(request):
    # Get the internal provider name URL variable.
    provider_name = request.matchdict.get('provider_name', 'openid')

    log.debug('provider_name: %s', provider_name)
    
    # Start the login procedure.
    response = Response()
    #response = request.response
    result = authomatic.login(WebObAdapter(request, response), provider_name)

    #log.debug('authomatic login result: %s', result)
    
    if result:
        if result.error:
            # Login procedure finished with an error.
            #request.session.flash('Sorry, login failed: %s' % (result.error.message))
            log.error('openid login failed: %s', result.error.message)
            #response.write(u'<h2>Login failed: {}</h2>'.format(result.error.message))
            response.text = render('phoenix:templates/forbidden.pt',
                                   {'message': result.error.message}, request=request)
        elif result.user:
            # Hooray, we have the user!
            log.debug("user=%s, id=%s, email=%s",
                      result.user.name, result.user.id, result.user.email)

            if is_valid_user(request, result.user.email):
                log.info("openid login successful for user %s", result.user.email)
                update_user(request, user_id=result.user.email, openid=result.user.id, activated=True)
                response.text = render('phoenix:templates/openid_success.pt',
                                       {'result': result},
                                       request=request)
                # Add the headers required to remember the user to the response
                response.headers.extend(remember(request, result.user.email))
            else:
                log.info("openid login: user %s is not registered", result.user.email)
                update_user(request, user_id=result.user.email, openid=result.user.id, activated=False)
                response.text = render('phoenix:templates/register.pt',
                                       {'email': result.user.email}, request=request)
    #log.debug('response: %s', response)
        
    return response

# home view
# ---------

@view_config(
    route_name='home',
    renderer='templates/home.pt',
    layout='default',
    permission='view'
    )
def home(request):
    lm = request.layout_manager
    lm.layout.add_heading('heading_info')
    lm.layout.add_heading('heading_stats')
    return dict()


# processes
# ---------

@view_config(
    route_name='processes',
    renderer='templates/form.pt',
    layout='default',
    permission='edit'
    )
class ProcessView(FormView):
    from .schema import ProcessSchema

    schema = ProcessSchema(title="Select process you wish to run")
    buttons = ('submit',)

    def submit_success(self, appstruct):
        params = self.schema.serialize(appstruct)
        identifier = params.get('process')
        
        session = self.request.session
        session['phoenix.process.identifier'] = identifier
        session.changed()
        
        return HTTPFound(location=self.request.route_url('execute'))
   
# jobs
# -------

@view_config(
    route_name='jobs',
    renderer='templates/jobs.pt',
    layout='default',
    permission='edit'
    )
def jobs(request):
    from .models import jobs_information

    jobs = jobs_information(request)

    #This block is used to allow viewing the data if javascript is deactivated
    from pyramid.request import Request
    #create a new request to jobsupdate
    subreq = Request.blank('/jobsupdate/starttime/inverted')
    #copy the cookie for authenication (else 403 error)
    subreq.cookies = request.cookies
    #Make the request
    response = request.invoke_subrequest(subreq)
    #Get the HTML part of the response
    noscriptform = response.body

    if "remove_all" in request.POST:
        from .models import drop_user_jobs
        drop_user_jobs(request)
        
        return HTTPFound(location=request.route_url('jobs'))

    elif "remove_selected" in request.POST:
        if("selected" in request.POST):
            from .models import drop_jobs_by_uuid
            drop_jobs_by_uuid(request,request.POST.getall("selected"))
        return HTTPFound(location=request.route_url('jobs'))

 
    return {"jobs":jobs,"noscriptform":noscriptform}

@view_config(
    route_name="jobsupdate",
    layout='default',
    permission='edit'
    )
def jobsupdate(request):
    from .models import jobs_information
    from .schema import TableSchema
    data = request.matchdict
    #Sort the table with the given key, matching to the template name
    key = data["sortkey"]
    #If inverted is found as type then the ordering is inverted.
    inverted = (data["type"]=="inverted")
    jobs = jobs_information(request,key,inverted)
    #Add HTML data for the table
    def tpd(key,value):
        return (key,{key:"<div id=\""+key+"\" onclick=\"sort(\'"+key+"\')\">"+value+"</div>"})
    table_options = 'id="process_table" class="table table-condensed accordion-group" style="table-layout: fixed; word-wrap: break-word;"'
    tableheader= [tpd('select','Select'),tpd('identifier','Identifier'),
                  tpd('starttime','Start Time'),tpd('duration','Duration'),
                  tpd('notes','Notes'),tpd('tags','Tags'),tpd('status','Status')]
    tablerows = []
    for job in jobs:
        tablerow = []
        job["select"] = '<input type="checkbox" name="selected" value="'+job['uuid']+'">'
        identifier = job["identifier"]
        uuid = job['uuid']
        job["identifier"] ='<a rel="tooltip" data-placement="right" title="ID:'+uuid+'">'+identifier+'</a>'
        for tuplepair in tableheader:
            key = tuplepair[0]
            tablerow.append(job[key])
        #overwrite the Status column
        perc = job.get("percent_completed")
        #A job once somehow had some undefined behaviour. The following code solved it. Now the
        #job is removed it is running without it. If the error occurs again find the reason for it.
        #and fix it.
        if perc == None:#the following value does not realy matter als long as it is an integer.
           perc = 0
        barwidth = 80
        barfill = perc*barwidth/100
        running = ('<a href="#" class="label label-info" data-toggle="popover"'+
                   ' data-placement="left" data-content="'+ str(job.get("status_message"))+
                   '" data-original-title="Status Message">'+job["status"]+'</a>\n'+
                   '<div><progress style="height:20px;width:'+str(barwidth)+'px;"  max="'+str(barwidth)+
                   '" value="'+str(barfill)+'"></progress>'+str(perc)+'%</div>')
        succeed = (' <a href="/output_details?uuid='+job["uuid"]+'" class="label label-success">'+
                   job["status"]+'</a>')
        failed = ('<a href="#" class="label label-warning" data-toggle="popover" data-placement="left"'+
                  'data-content="'+job["error_message"]+'" data-original-title="Error Message">'+
                  job["status"]+'</a>')
        exception = ('<a href="#" class="label label-important" data-toggle="popover"'+
                    ' data-placement="left" data-content="'+job["error_message"]+
                    '" data-original-title="Error Message">'+job["status"]+'</a>')
        #The last element is status
        tablerow[-1] = (job['status'],{
            'ProcessAccepted':running, 'ProcessStarted':running, 'ProcessPaused':running,
            'ProcessSucceeded': succeed, 'ProcessFailed':failed, 'Exception': exception })
        tablerows.append(tablerow)
    #Create a form using the HTML data above and using the TableSchema
    appstruct = {'table':{'tableheader':tableheader, 'tablerows':tablerows,
        'table_options':table_options}}
    schema = TableSchema().bind()
    schema.set_title("My Jobs")
    myForm = Form(schema,buttons=("remove selected","remove all"))
    form = myForm.render(appstruct=appstruct)
    #Change the layout from horizontal to vertical to allow the table take the full width.
    form = form.replace('deform form-horizontal','deform form-vertical')
    return Response(form,content_type='text/html')

# output_details
# --------------

@view_config(
     route_name='output_details',
     renderer='templates/output_details.pt',
     layout='default',
     permission='edit')
def output_details(request):
    title = u"Process Outputs"

    from .models import get_job
    job = get_job(request, uuid=request.params.get('uuid'))
    wps = WebProcessingService(job['service_url'], verbose=False)
    execution = WPSExecution(url=wps.url)
    execution.checkStatus(url=job['status_location'], sleepSecs=0)

    form_info="Status: %s" % (execution.status)
    
    return( dict(
        title=execution.process.title, 
        form_info=form_info,
        outputs=execution.processOutputs) )

# form
# -----

@view_config(
    route_name='execute',
    renderer='templates/form.pt',
    layout='default',
    permission='edit'
    )
class ExecuteView(FormView):
    buttons = ('submit',)
    schema_factory = None
    wps = None
   
    def __call__(self):
        # build the schema if it not exist
        if self.schema is None:
            if self.schema_factory is None:
                self.schema_factory = WPSSchema
            
        try:
            session = self.request.session
            identifier = session['phoenix.process.identifier']
            self.wps = WebProcessingService(wps_url(self.request), verbose=False)
            process = self.wps.describeprocess(identifier)
            self.schema = self.schema_factory(
                info = True,
                title = process.title,
                process = process)
        except:
            raise
       
        return super(ExecuteView, self).__call__()

    def appstruct(self):
        return None

    def submit_success(self, appstruct):
        session = self.request.session
        identifier = session['phoenix.process.identifier']
        params = self.schema.serialize(appstruct)
      
        execution = execute_wps(self.wps, identifier, params)

        from .models import add_job
        add_job(
            request = self.request, 
            user_id = authenticated_userid(self.request), 
            identifier = identifier, 
            wps_url = self.wps.url, 
            execution = execution,
            notes = params.get('info_notes', ''),
            tags = params.get('info_tags', ''))

        return HTTPFound(location=self.request.route_url('jobs'))

@view_config(
    route_name='monitor',
    renderer='templates/embedded.pt',
    layout='default',
    permission='admin'
    )
def monitor(request):
    return dict(external_url=supervisor_url(request))

@view_config(
    route_name='tds',
    renderer='templates/embedded.pt',
    layout='default',
    permission='edit'
    )
def thredds(request):
    return dict(external_url=thredds_url(request))

@view_config(
    route_name='catalog_wps_add',
    renderer='templates/catalog.pt',
    layout='default',
    permission='edit',
    )
class CatalogAddWPSView(FormView):
    #form_info = "Hover your mouse over the widgets for description."
    schema = None
    schema_factory = None
    buttons = ('add',)
    title = u"Catalog"

    def __call__(self):
        csw = CatalogueServiceWeb(csw_url(self.request))
        csw.getrecords2(maxrecords=100)
        wps_list = []
        for rec_id in csw.records:
            rec = csw.records[rec_id]
            if rec.format == 'WPS':
                wps_list.append((rec.references[0]['url'], rec.title))

        from .schema import CatalogAddWPSSchema
        # build the schema if it does not exist
        if self.schema is None:
            if self.schema_factory is None:
                self.schema_factory = CatalogAddWPSSchema
            self.schema = self.schema_factory(title='Catalog').bind(
                wps_list = wps_list,
                readonly = True)

        return super(CatalogAddWPSView, self).__call__()

    def appstruct(self):
        return {'current_wps' : wps_url(self.request)}

    def add_success(self, appstruct):
        serialized = self.schema.serialize(appstruct)
        url = serialized['new_wps']

        csw = CatalogueServiceWeb(csw_url(self.request))
        try:
            csw.harvest(url, 'http://www.opengis.net/wps/1.0.0')
        except:
            log.error("Could not add wps service to catalog: %s" % (url))
            #raise

        return HTTPFound(location=self.request.route_url('catalog_wps_add'))

@view_config(
    route_name='catalog_wps_select',
    renderer='templates/catalog.pt',
    layout='default',
    permission='edit',
    )
class CatalogSelectWPSView(FormView):
    schema = None
    schema_factory = None
    buttons = ('submit',)
    title = u"Catalog"

    def __call__(self):
        csw = CatalogueServiceWeb(csw_url(self.request))
        csw.getrecords2(maxrecords=100)
        wps_list = []
        for rec_id in csw.records:
            rec = csw.records[rec_id]
            if rec.format == 'WPS':
                wps_list.append((rec.references[0]['url'], rec.title))

        from .schema import CatalogSelectWPSSchema
        # build the schema if it not exist
        if self.schema is None:
            if self.schema_factory is None:
                self.schema_factory = CatalogSelectWPSSchema
            self.schema = self.schema_factory(title='Catalog').bind(wps_list = wps_list)

        return super(CatalogSelectWPSView, self).__call__()

    def appstruct(self):
        return {'active_wps' : wps_url(self.request)}

    def submit_success(self, appstruct):
        serialized = self.schema.serialize(appstruct)
        wps_id = serialized['active_wps']
        #log.debug('wps_id = %s', wps_id)
        update_wps_url(self.request, wps_id)        

        return HTTPFound(location=self.request.route_url('processes'))

@view_config(
    route_name='admin_user_edit',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserEditView(FormView):
    from .schema import AdminUserEditSchema
    
    schema = AdminUserEditSchema()
    buttons = ('edit',)
    title = u"Manage Users"

    def appstruct(self):
        return {}

    def edit_success(self, appstruct):
        params = self.schema.serialize(appstruct)
        user_id = params.get('user_id').pop()

        log.debug("edit users %s", user_id)

        session = self.request.session
        session['phoenix.admin.edit.user_id'] = user_id
        session.changed()

        return HTTPFound(location=self.request.route_url('admin_user_edit_task'))

@view_config(
    route_name='admin_user_edit_task',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserEditTaskView(FormView):
    from .schema import AdminUserEditTaskSchema
    
    schema = AdminUserEditTaskSchema()
    buttons = ('update', 'cancel',)
    title = u"Edit User"

    def appstruct(self):
        from .models import user_with_id
        session = self.request.session
        user_id = session['phoenix.admin.edit.user_id']
        user = user_with_id(self.request, user_id=user_id)
        return dict(
            email = user_id,
            openid = user.get('openid'),
            name = user.get('name'),
            organisation = user.get('organisation'),
            notes = user.get('notes'),
            activated = user.get('activated'),
            )

    def update_success(self, appstruct):
        from .models import update_user
        user = self.schema.serialize(appstruct)
        session = self.request.session
        user_id = session['phoenix.admin.edit.user_id']
        #log.debug("user activated: %s", user.get('activated') == 'true')
        update_user(self.request,
                      user_id = user_id,
                      openid = user.get('openid'),
                      name = user.get('name'),
                      organisation = user.get('organisation'),
                      notes = user.get('notes'),
                      activated = user.get('activated') == 'true')

        return HTTPFound(location=self.request.route_url('admin_user_edit'))
    
    def cancel_success(self, appstruct):
        return HTTPFound(location=self.request.route_url('admin_user_edit'))


@view_config(
    route_name='admin_user_register',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserRegisterView(FormView):
    from .schema import AdminUserRegisterSchema
    
    schema = AdminUserRegisterSchema()
    buttons = ('register',)
    title = u"Register User"

    def appstruct(self):
        return {}

    def register_success(self, appstruct):
        from .models import register_user
        user = self.schema.serialize(appstruct)
        register_user(self.request,
                      user_id = user.get('email'),
                      openid = user.get('openid'),
                      name = user.get('name'),
                      organisation = user.get('organisation'),
                      notes = user.get('notes'),
                      activated = True)

        return HTTPFound(location=self.request.route_url('admin_user_register'))

@view_config(
    route_name='admin_user_unregister',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserUnregisterView(FormView):
    from .schema import AdminUserUnregisterSchema
    
    schema = AdminUserUnregisterSchema()
    buttons = ('unregister',)
    title = u"Unregister User"

    def unregister_success(self, appstruct):
        from .models import unregister_user
        params = self.schema.serialize(appstruct)
        for user_id in params.get('user_id', []):
            unregister_user(self.request, user_id=user_id)
        
        return HTTPFound(location=self.request.route_url('admin_user_unregister'))

@view_config(
    route_name='admin_user_activate',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserActivateView(FormView):
    from .schema import AdminUserActivateSchema
    
    schema = AdminUserActivateSchema()
    buttons = ('activate',)
    title = u"Activate Users"
    
    def activate_success(self, appstruct):
        from .models import activate_user
        params = self.schema.serialize(appstruct)
        for user_id in params.get('user_id', []):
            activate_user(self.request, user_id=user_id)

        return HTTPFound(location=self.request.route_url('admin_user_activate'))

@view_config(
    route_name='admin_user_deactivate',
    renderer='templates/admin.pt',
    layout='default',
    permission='edit',
    )
class AdminUserDeactivateView(FormView):
    from .schema import AdminUserDeactivateSchema
    
    schema = AdminUserDeactivateSchema()
    buttons = ('deactivate',)
    title = u"Deactivate Users"

    def deactivate_success(self, appstruct):
        from .models import deactivate_user
        params = self.schema.serialize(appstruct)
        for user_id in params.get('user_id', []):
            log.debug('deactivate user %s', user_id)
            deactivate_user(self.request, user_id=user_id)

        return HTTPFound(location=self.request.route_url('admin_user_deactivate'))

@view_config(
    route_name='map',
    renderer='templates/map.pt',
    layout='default',
    permission='edit'
    )
def map(request):
    from .models import user_openid
    return dict(openid=user_openid(request, authenticated_userid(request)))

@view_config(
    route_name='help',
    renderer='templates/embedded.pt',
    layout='default',
    permission='view'
    )
def help(request):
    return dict(external_url='/docs')

