import dateparser

from pyramid.view import view_config, view_defaults
from pyramid.httpexceptions import HTTPFound
from deform import Form, Button
from deform import ValidationFailure

from phoenix.events import JobStarted
from phoenix.views import MyView
from phoenix.wps import appstruct_to_inputs
from phoenix.wps import WPSSchema
from phoenix.utils import wps_describe_url
from phoenix.security import check_csrf_token
from phoenix.ceda_security import check_ceda_permissions

from owslib.wps import WebProcessingService
from owslib.wps import WPSExecution
from owslib.wps import ComplexDataInput, BoundingBoxDataInput

from time import sleep

import logging
LOGGER = logging.getLogger("PHOENIX")


@view_defaults(permission='view', layout='default')
class ExecuteProcess(MyView):
    def __init__(self, request):
        self.request = request
        self.execution = None
        self.service_id = None
        self.processid = None
        self.process = None
        self.service_id = request.params.get('wps')
        self.processid = request.params.get('process')
        # TODO: avoid getcaps
        self.service = request.catalog.get_record_by_id(self.service_id)
        self.wps = WebProcessingService(
            url=self.service.url,
            verify=False)
        # TODO: need to fix owslib to handle special identifiers
        self.process = self.wps.describeprocess(self.processid)
        super(ExecuteProcess, self).__init__(request, name='processes_execute', title='')

    def has_execute_permission(self):
        ceda_permission = check_ceda_permissions(self.request, self.request.user, self.processid)
        return self.service.public or (self.request.has_permission('submit') and ceda_permission)

    def breadcrumbs(self):
        breadcrumbs = super(ExecuteProcess, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path('processes'), title='Processes'))
        breadcrumbs.append(dict(route_path=self.request.route_path(
            'processes_list', _query=[('wps', self.service_id)]),
            title=self.service.title))
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.process.identifier))
        return breadcrumbs

    def appstruct(self):
        # TODO: not a nice way to get inputs ... should be cleaned up in owslib
        result = {}
        if self.execution:
            for inp in self.execution.dataInputs:
                if inp.data or inp.reference:
                    if inp.identifier not in result:
                        # init result for param with empty list
                        result[inp.identifier] = []
                    if inp.data:
                        # add literal input, inp.data is a list
                        result[inp.identifier].extend(inp.data)
                    elif inp.reference:
                        # add reference to complex input
                        result[inp.identifier].append(inp.reference)
        for inp in self.process.dataInputs:
            # TODO: dupliate code in wizard.start
            # convert boolean
            if 'boolean' in inp.dataType and inp.identifier in result:
                result[inp.identifier] = [val.lower() == 'true' for val in result[inp.identifier]]
            elif 'dateTime' in inp.dataType and inp.identifier in result:
                result[inp.identifier] = [dateparser.parse(val) for val in result[inp.identifier]]
            elif 'date' in inp.dataType and inp.identifier in result:
                result[inp.identifier] = [dateparser.parse(val) for val in result[inp.identifier]]
            elif 'time' in inp.dataType and inp.identifier in result:
                result[inp.identifier] = [dateparser.parse(val) for val in result[inp.identifier]]
            elif inp.dataType == 'BoundingBoxData' and inp.identifier in result:
                result[inp.identifier] = [
                    "{0.minx},{0.miny},{0.maxx},{0.maxy}".format(bbox) for bbox in result[inp.identifier]]
            # TODO: very dirty ... if single value then take the first
            if inp.maxOccurs < 2 and inp.identifier in result:
                result[inp.identifier] = result[inp.identifier][0]
        return result

    def generate_form(self, formid='deform'):
        schema = WPSSchema(request=self.request,
                           process=self.process,
                           use_async=self.request.has_permission('admin'),
                           user=self.request.user)
        submit_button = Button(name='submit', title='Submit',
                               css_class='btn btn-success btn-lg btn-block',
                               disabled=not self.has_execute_permission())
        return Form(
            schema.bind(request=self.request),
            buttons=(submit_button,),
            formid=formid,
        )

    def process_form(self, form):
        controls = list(self.request.POST.items())
        try:
            # TODO: uploader puts qqfile in controls
            controls = [control for control in controls if 'qqfile' not in control[0]]
            LOGGER.debug("before validate %s", controls)
            appstruct = form.validate(controls)
            LOGGER.debug("before execute %s", appstruct)
            job_id = self.execute(appstruct)
        except ValidationFailure as e:
            self.session.flash("Page validation failed.", queue='danger')
            return dict(process=self.process,
                        url=wps_describe_url(self.wps.url, self.processid),
                        form=e.render())
        else:
            if not self.request.user:  # not logged-in
                return HTTPFound(location=self.request.route_url('job_status', job_id=job_id))
            else:
                return HTTPFound(location=self.request.route_url('monitor'))

    def execute(self, appstruct):
        inputs = appstruct_to_inputs(self.request, appstruct)
        # need to use ComplexDataInput
        complex_inpts = {}
        bbox_inpts = []
        for inpt in self.process.dataInputs:
            if 'ComplexData' in inpt.dataType:
                complex_inpts[inpt.identifier] = inpt
            elif 'BoundingBoxData' in inpt.dataType:
                bbox_inpts.append(inpt.identifier)
        new_inputs = []
        for inpt in inputs:
            identifier = inpt[0]
            value = inpt[1]
            if identifier in complex_inpts:
                new_inputs.append((identifier, ComplexDataInput(value)))
            elif identifier in bbox_inpts:
                crs = 'urn:ogc:def:crs:OGC:2:84'
                new_inputs.append((identifier, BoundingBoxDataInput(value, crs=crs)))
            else:
                new_inputs.append(inpt)
        inputs = new_inputs
        # prepare outputs
        outputs = []
        for output in self.process.processOutputs:
            outputs.append(
                (output.identifier, output.dataType == 'ComplexData'))

        from phoenix.tasks.execute import execute_process
        result = execute_process.delay(
            userid=self.request.unauthenticated_userid,
            url=self.wps.url,
            service_name=self.service.title,
            identifier=self.process.identifier,
            inputs=inputs,
            outputs=outputs,
            use_async=appstruct.get('_async_check', True))

        # give the job a chance to start
        sleep(1)
        self.request.registry.notify(JobStarted(self.request, result.id))
        LOGGER.debug('wps url={}'.format(self.wps.url))
        LOGGER.debug('request inputs = {}'.format(str(inputs)))
        return result.id

    @view_config(
        route_name='processes_execute',
        renderer='phoenix:processes/templates/processes/execute.pt',
        accept='text/html')
    def view(self):
        form = self.generate_form()
        if 'submit' in self.request.POST:
            check_csrf_token(self.request)
            return self.process_form(form)
        if not self.has_execute_permission():
            if self.request.user is not None:
                msg = """<strong>Warning:</strong> You are not allowed to run this
                process as you do not have access to the datasets. Please contact the
                CEDA Helpdesk for more information about applying for access to the
                required resources. Include a copy of the URL above to indicate which
                resources you are trying to access."""
            else:
                msg = """<strong>Warning:</strong> You are not allowed to run this process.
                Please <a href="{0}" class="alert-link">sign in</a> and wait for account activation."""
                msg = msg.format(self.request.route_path('sign_in'))
            self.session.flash(msg, queue='warning')
        return dict(
            process=self.process,
            url=wps_describe_url(self.wps.url, self.processid),
            form=form.render(self.appstruct()))
