from pyramid.view import view_config
from pyramid.security import authenticated_userid
import json

from phoenix.views.wizard import Wizard

import logging
logger = logging.getLogger(__name__)

class Done(Wizard):
    def __init__(self, request):
        super(Done, self).__init__(
            request, name='wizard_done', title="Done")
        self.description = "Describe your Job and start Workflow."
        from owslib.wps import WebProcessingService
        self.wps = WebProcessingService(self.wizard_state.get('wizard_wps')['url'])
        self.csw = self.request.csw

    def breadcrumbs(self):
        breadcrumbs = super(Done, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs

    def schema(self):
        from phoenix.schema import DoneSchema
        return DoneSchema()

    def workflow_description(self):
        # source_type
        source_type = self.wizard_state.get('wizard_source')['source']
        workflow = dict(name=source_type, source={}, worker={})

        # source
        user = self.get_user()
        if 'swift' in source_type:
            source = dict(
                storage_url = user.get('swift_storage_url'),
                auth_token = user.get('swift_auth_token'),
            )
            source['container'] = self.wizard_state.get('wizard_swiftbrowser')['container']
            source['prefix'] = self.wizard_state.get('wizard_swiftbrowser')['prefix']
            workflow['source']['swift'] = source
        else: # esgf
            selection = self.wizard_state.get('wizard_esgf_search')['selection']
            source = json.loads(selection)
            source['credentials'] = user.get('credentials')
            workflow['source']['esgf'] = source

        # worker
        from phoenix.utils import appstruct_to_inputs
        inputs = appstruct_to_inputs(self.wizard_state.get('wizard_literal_inputs', {}))
        worker_inputs = ['%s=%s' % (key, value) for key,value in inputs]
        worker = dict(
            url = self.wps.url,
            identifier = self.wizard_state.get('wizard_process')['identifier'],
            inputs = [(key, value) for key,value in inputs],
            resource = self.wizard_state.get('wizard_complex_inputs')['identifier'],
            )
        workflow['worker'] = worker
        return workflow

    def success(self, appstruct):
        super(Done, self).success(appstruct)
        if appstruct.get('is_favorite', False):
            self.favorite.set(
                name=appstruct.get('favorite_name'),
                state=self.wizard_state.dump())
            self.favorite.save()

        from phoenix.tasks import execute_workflow
        execute_workflow.delay(authenticated_userid(self.request), self.request.wps.url,
                               workflow=self.workflow_description())
        
    def next_success(self, appstruct):
        from pyramid.httpexceptions import HTTPFound
        self.success(appstruct)
        self.wizard_state.clear()
        return HTTPFound(location=self.request.route_url('monitor'))

    def appstruct(self):
        appstruct = super(Done, self).appstruct()
        #params = ', '.join(['%s=%s' % item for item in self.wizard_state.get('wizard_literal_inputs', {}).items()])
        identifier = self.wizard_state.get('wizard_process')['identifier']
        appstruct.update( dict(favorite_name=identifier) )
        return appstruct

    @view_config(route_name='wizard_done', renderer='phoenix:templates/wizard/default.pt')
    def view(self):
        return super(Done, self).view()
