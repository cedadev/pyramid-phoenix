from pyramid.view import view_config, view_defaults

from pyramid.httpexceptions import HTTPException, HTTPFound, HTTPNotFound
from deform import Form, Button
from deform import ValidationFailure

from phoenix.views.processes import Processes

from owslib.wps import WebProcessingService

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='submit', layout='default')
class ExecuteProcess(Processes):
    def __init__(self, request):
        url = request.session.get('wps_url')
        # TODO: fix owslib.wps url handling
        url = url.split('?')[0]
        self.wps = WebProcessingService(url)
        identifier = request.params.get('identifier')
        logger.debug("execute: url=%s, identifier=%s", url, identifier)
        # TODO: need to fix owslib to handle special identifiers
        self.process = self.wps.describeprocess(identifier)
        super(ExecuteProcess, self).__init__(request, name='processes_execute', title='')

    def breadcrumbs(self):
        breadcrumbs = super(ExecuteProcess, self).breadcrumbs()
        route_path = self.request.route_path('processes_list')
        breadcrumbs.append(dict(route_path=route_path, title=self.wps.identification.title))
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.process.title))
        return breadcrumbs

    def appstruct(self):
        return {}

    def generate_form(self, formid='deform'):
        from phoenix.schema.wps import WPSSchema
        schema = WPSSchema(process = self.process, user=self.get_user())
        return Form(
            schema,
            buttons=('submit',),
            formid=formid,
            )
    
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.execute(appstruct)
        except ValidationFailure, e:
            logger.exception('validation of exectue view failed.')
            self.session.flash("There are errors on this page.", queue='danger')
            return dict(form = e.render())
        return HTTPFound(location=self.request.route_url('myjobs'))

    def execute(self, appstruct):
        from phoenix.utils import appstruct_to_inputs
        inputs = appstruct_to_inputs(appstruct)
        outputs = []
        for output in self.process.processOutputs:
            outputs.append( (output.identifier, output.dataType == 'ComplexData' ) )

            from phoenix.tasks import execute
            execute.delay(self.user_email(), self.wps.url, self.process.identifier, 
                          inputs=inputs, outputs=outputs)
    
    @view_config(route_name='processes_execute', renderer='phoenix:templates/processes/execute.pt')
    def view(self):
        form = self.generate_form()
        if 'submit' in self.request.POST:
            return self.process_form(form)
        return dict(
            description=getattr(self.process, 'abstract', ''),
            form=form.render(self.appstruct()))
    
