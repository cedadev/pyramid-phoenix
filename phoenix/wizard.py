from pyramid.view import view_config, view_defaults
from pyramid.httpexceptions import HTTPFound
from pyramid.security import authenticated_userid

from deform import Form, Button
from deform import ValidationFailure

from owslib.wps import WebProcessingService

import models

import logging
logger = logging.getLogger(__name__)

class WizardState(object):
    def __init__(self, session, initial_step, final_step='wizard_done'):
        self.session = session
        self.initial_step = initial_step
        self.final_step = final_step
        if not 'wizard' in self.session:
            self.clear()
            
    def current_step(self):
        step = self.initial_step
        if len(self.session['wizard']['chain']) > 0:
            step = self.session['wizard']['chain'][-1]
        return step

    def is_first(self):
        return self.current_step() == self.initial_step

    def is_last(self):
        return self.current_step() == self.final_step

    def next(self, step):
        self.session['wizard']['chain'].append(step)
        self.session.changed()

    def previous(self):
        if len(self.session['wizard']['chain']) > 1:
            self.session['wizard']['chain'].pop()
            self.session.changed()

    def get(self, key, default=None):
        if not key in self.session['wizard']['state']:
            self.session['wizard']['state'][key] = default
            self.session.changed()
        return self.session['wizard']['state'].get(key)

    def set(self, key, value):
        self.session['wizard']['state'][key] = value
        self.session.changed()

    def clear(self):
        self.session['wizard'] = dict(state={}, chain=[self.initial_step])
        self.session.changed()

@view_defaults(permission='view', layout='default')
class Wizard(object):
    def __init__(self, request, title, description=''):
        self.request = request
        self.title = title
        self.description = description
        self.session = self.request.session
        self.csw = self.request.csw
        self.catalogdb = models.Catalog(self.request)
        self.wizard_state = WizardState(self.session, 'wizard_wps')

    def buttons(self):
        prev_disabled = not self.prev_ok()
        next_disabled = not self.next_ok()

        prev_button = Button(name='previous', title='Previous',
                             disabled=prev_disabled)   #type=submit|reset|button,value=name,css_type="btn-..."
        next_button = Button(name='next', title='Next',
                             disabled=next_disabled)
        done_button = Button(name='next', title='Done',
                             disabled=next_disabled)
        cancel_button = Button(name='cancel', title='Cancel',
                               disabled=False)
        buttons = []
        if not self.wizard_state.is_first():
            buttons.append(prev_button)
        if self.wizard_state.is_last():
            buttons.append(done_button)
        else:
            buttons.append(next_button)
        buttons.append(cancel_button)
        return buttons

    def prev_ok(self):
        return True

    def next_ok(self):
        return True
    
    def use_ajax(self):
        return False

    def ajax_options(self):
        options = """
        {success:
           function (rText, sText, xhr, form) {
             deform.processCallbacks();
             deform.focusFirstInput();
             var loc = xhr.getResponseHeader('X-Relocate');
                if (loc) {
                  document.location = loc;
                };
             }
        }
        """
        return '{}'

    def previous(self):
        self.wizard_state.previous()
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

    def next(self, step):
        self.wizard_state.next(step)
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

    def cancel(self):
        self.wizard_state.clear()
        return HTTPFound(location=self.request.route_url(self.wizard_state.current_step()))

class ChooseWPS(Wizard):
    def __init__(self, request):
        super(ChooseWPS, self).__init__(request, 'Choose WPS')

    def generate_form(self, formid='deform'):
        from .schema import ChooseWPSSchema
        schema = ChooseWPSSchema().bind(wps_list = self.catalogdb.all())
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('wps_url', appstruct.get('url'))
        except ValidationFailure, e:
            logger.exception('validation of wps view failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_process')

    def appstruct(self):
        return dict(url=self.wizard_state.get('wps_url'))

    @view_config(route_name='wizard_wps', renderer='templates/wizard/default.pt')
    def choose_wps_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class ChooseWPSProcess(Wizard):
    def __init__(self, request):
        super(ChooseWPSProcess, self).__init__(request, 'Choose WPS Process')
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))

    def generate_form(self, formid='deform'):
        from .schema import SelectProcessSchema
        schema = SelectProcessSchema().bind(processes = self.wps.processes)
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('process_identifier', appstruct.get('identifier'))
        except ValidationFailure, e:
            logger.exception('validation of process view failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_literal_inputs')

    def appstruct(self):
        return dict(identifier=self.wizard_state.get('process_identifier'))

    @view_config(route_name='wizard_process', renderer='templates/wizard/default.pt')
    def select_process_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class LiteralInputs(Wizard):
    def __init__(self, request):
        super(LiteralInputs, self).__init__(
            request,
            "Literal Inputs",
            "")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.process = self.wps.describeprocess(self.wizard_state.get('process_identifier'))

    def generate_form(self, formid='deform'):
        from .wps import WPSSchema
        schema = WPSSchema(info=True, hide=True, process = self.process)
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('literal_inputs', appstruct)
        except ValidationFailure, e:
            logger.exception('validation of process parameter failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_complex_inputs')

    def appstruct(self):
        return self.wizard_state.get('literal_inputs', {})

    @view_config(route_name='wizard_literal_inputs', renderer='templates/wizard/default.pt')
    def literal_inputs_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class ComplexInputs(Wizard):
    def __init__(self, request):
        super(ComplexInputs, self).__init__(
            request,
            "Choose Complex Input Parameter",
            "")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))
        self.process = self.wps.describeprocess(self.wizard_state.get('process_identifier'))

    def generate_form(self, formid='deform'):
        from .schema import ChooseInputParamterSchema
        schema = ChooseInputParamterSchema().bind(process=self.process)
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('complex_input_identifier', appstruct.get('identifier'))
        except ValidationFailure, e:
            logger.exception('validation of process parameter failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_source')

    def appstruct(self):
        return dict(identifier=self.wizard_state.get('complex_input_identifier'))

    @view_config(route_name='wizard_complex_inputs', renderer='templates/wizard/default.pt')
    def complex_parameters_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class ChooseSource(Wizard):
    def __init__(self, request):
        super(ChooseSource, self).__init__(
            request,
            "Choose Source",
            "")

    def generate_form(self, formid='deform'):
        from .schema import ChooseSourceSchema
        schema = ChooseSourceSchema()
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('source', appstruct.get('source'))
        except ValidationFailure, e:
            logger.exception('validation of process parameter failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next( self.wizard_state.get('source') )

    def appstruct(self):
        return dict(source=self.wizard_state.get('source'))

    @view_config(route_name='wizard_source', renderer='templates/wizard/default.pt')
    def choose_source_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))
    
class CatalogSearch(Wizard):
    def __init__(self, request):
        super(CatalogSearch, self).__init__(
            request,
            "Catalog Search",
            "Search in CSW Catalog Service")

    def search_csw(self, query=''):
        keywords = [k for k in map(str.strip, str(query).split(' ')) if len(k)>0]

        results = []
        try:
            self.csw.getrecords(keywords=keywords)
            logger.debug('csw results %s', self.csw.results)
            for rec in self.csw.records:
                myrec = self.csw.records[rec]
                results.append(dict(
                    identifier = myrec.identifier,
                    title = myrec.title,
                    abstract = myrec.abstract,
                    subjects = myrec.subjects,
                    format = myrec.format,
                    creator = myrec.creator,
                    modified = myrec.modified,
                    bbox = myrec.bbox,
                    ))
        except:
            logger.exception('could not get items for csw.')
        return results
        
    @view_config(renderer='json', name='select.csw')
    def select_csw(self):
        # TODO: refactor this ... not efficient
        identifier = self.request.params.get('identifier', None)
        logger.debug('called with %s', identifier)
        if identifier is not None:
            selection = self.wizard_state.get('csw_selection', [])
            if identifier in selection:
                selection.remove(identifier)
            else:
                selection.append(identifier)
            self.wizard_state.set('csw_selection', selection)
        return {}

    def appstruct(self):
        return dict(csw_selection=self.wizard_state.get('csw_selection'))

    @view_config(route_name='wizard_csw', renderer='templates/wizard/csw.pt')
    def csw_view(self):
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.next( 'wizard_done' )
        elif 'cancel' in self.request.POST:
            return self.cancel()

        query = self.request.params.get('query', None)
        checkbox = self.request.params.get('checkbox', None)
        logger.debug(checkbox)
        items = self.search_csw(query)
        for item in items:            
            if item['identifier'] in self.wizard_state.get('csw_selection', []):
                item['selected'] = True
            else:
                item['selected'] = False

        from .grid import CatalogSearchGrid    
        grid = CatalogSearchGrid(
                self.request,
                items,
                ['title', 'subjects', 'selected'],
            )

        return dict(
            title=self.title, 
            description=self.description,
            grid=grid,
            items=items,
        )

class ESGFSearch(Wizard):
    def __init__(self, request):
        super(ESGFSearch, self).__init__(
            request,
            "ESGF Search",
            "")

    def generate_form(self, formid='deform'):
        from .schema import ESGFSearchSchema
        schema = ESGFSearchSchema()
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            logger.debug("esgf selection = %s", appstruct)
            self.wizard_state.set('esgf_selection', appstruct.get('selection'))
        except ValidationFailure, e:
            logger.exception('validation of process parameter failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_esgf_files')

    def appstruct(self):
        return dict(selection=self.wizard_state.get('esgf_selection', {}))

    @view_config(route_name='wizard_esgf', renderer='templates/wizard/esgf.pt')
    def esgf_search_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class ESGFFileSearch(Wizard):
    def __init__(self, request):
        super(ESGFFileSearch, self).__init__(
            request,
            "ESGF File Search",
            "")

    def generate_form(self, formid='deform'):
        from .schema import ESGFFilesSchema
        schema = ESGFFilesSchema().bind(selection=self.wizard_state.get('esgf_selection'))
        return Form(
            schema,
            buttons=self.buttons(),
            formid=formid,
            use_ajax=self.use_ajax(),
            ajax_options=self.ajax_options(),
            )
    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            appstruct = form.validate(controls)
            self.wizard_state.set('esgf_files', appstruct.get('url'))
        except ValidationFailure, e:
            logger.exception('validation failed.')
            return dict(title=self.title, description=self.description, form=e.render())
        return self.next('wizard_done')

    def appstruct(self):
        return dict(url=self.wizard_state.get('esgf_files'))

    @view_config(route_name='wizard_esgf_files', renderer='templates/wizard/esgf.pt')
    def esgf_file_search_view(self):
        form = self.generate_form()
        
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'next' in self.request.POST:
            return self.process_form(form)
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title,
            description=self.description,
            form=form.render(self.appstruct()))

class Done(Wizard):
    def __init__(self, request):
        super(Done, self).__init__(
            request,
            "Done",
            "Check Parameters and start WPS Process")
        self.wps = WebProcessingService(self.wizard_state.get('wps_url'))

    def convert_states_to_nodes(self):
        userdb = models.User(self.request)
        credentials = userdb.credentials(authenticated_userid(self.request))

        source = dict(
            service = self.request.wps.url,
            identifier = 'esgf_wget',
            input = ['credentials=%s' % (credentials)],
            output = ['output'],
            sources = [[str(file_url)] for file_url in self.wizard_state.get('esgf_files')])
        worker_inputs = map(lambda x: str(x[0]) + '=' + str(x[1]),  self.wizard_state.get('literal_inputs').items())
        worker = dict(
            service = self.wps.url,
            identifier = self.wizard_state.get('process_identifier'),
            input = worker_inputs,
            output = ['output'])
        nodes = dict(source=source, worker=worker)
        return nodes

    def done(self):
        identifier = self.wizard_state.get('process_identifier')
        inputs = self.wizard_state.get('literal_inputs').items()
        complex_input = self.wizard_state.get('complex_input_identifier')
        notes = self.wizard_state.get('literal_inputs')['info_notes']
        tags = self.wizard_state.get('literal_inputs')['info_tags']

        execution = None
        if self.wizard_state.get('source') == 'wizard_csw':
            for url in self.wizard_state.get('csw_selection'):
                inputs.append( (complex_input, url) )
            inputs = [(str(key), str(value)) for key, value in inputs]
            outputs = [("output",True)]
            execution = self.wps.execute(identifier, inputs=inputs, output=outputs)
        else:
            nodes = self.convert_states_to_nodes()
            from .wps import execute_restflow
            execution = execute_restflow(self.request.wps, nodes)

        models.add_job(
            request = self.request,
            user_id = authenticated_userid(self.request), 
            identifier = identifier,
            wps_url = self.wps.url,
            execution = execution,
            notes = notes,
            tags = tags)
                
        return HTTPFound(location=self.request.route_url('jobs'))

    @view_config(route_name='wizard_done', renderer='templates/wizard/done.pt')
    def done_view(self):
        if 'previous' in self.request.POST:
            return self.previous()
        elif 'done' in self.request.POST:
            return self.done()
        elif 'cancel' in self.request.POST:
            return self.cancel()

        return dict(
            title=self.title, 
            description=self.description,
            )
