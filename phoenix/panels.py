from pyramid_layout.panel import panel_config
from pyramid.renderers import render

from phoenix.utils import root_path

import logging
logger = logging.getLogger(__name__)


@panel_config(name='navbar')
def navbar(context, request):
    def nav_item(name, url, icon=None):
        active = root_path(request.current_route_path()) == root_path(url)
        return dict(name=name, url=url, active=active, icon=icon)

    items = list()
    items.append(nav_item('Processes', request.route_path('processes')))
    if request.has_permission('edit'):
        items.append(nav_item('Monitor', request.route_path('monitor')))

    subitems = list()
    subitems.append(nav_item('Dashboard', request.route_path('dashboard', tab='overview'), icon='fa fa-dashboard'))
    
    return render(
        'phoenix:templates/panels/navbar.pt',  
        {'items': items,
         'subitems': subitems},              
        request                                   
    )


@panel_config(name='messages')
def messages(context, request):
    return render(
        'phoenix:templates/panels/messages.pt',  
        dict(),             
        request                    
    )


@panel_config(name='breadcrumbs')
def breadcrumbs(context, request):
    lm = request.layout_manager
    if not lm or not lm.layout:
        breadcrumbs = []
    else:
        breadcrumbs = lm.layout.breadcrumbs

    return render(
        'phoenix:templates/panels/breadcrumbs.pt', 
        {'breadcrumbs': breadcrumbs},             
        request                                    
    )


@panel_config(name='footer')
def footer(context, request):
    from phoenix import __version__ as version

    return render(
        'phoenix:templates/panels/footer.pt',  
        {'version': version},             
        request                                    
    )   
    
    


@panel_config(name='headings')
def headings(context, request):
    lm = request.layout_manager
    layout = lm.layout
    if layout.headings:
        return '\n'.join([lm.render_panel(name, *args, **kw) for name, args, kw in layout.headings])
    return ''

def includeme(config):
    config.add_panel('phoenix.panels.breadcrumbs', 'breadcrumbs')
    config.add_panel('phoenix.panels.navbar', 'navbar')
    config.add_panel('phoenix.panels.footer', 'footer')
    config.add_panel('phoenix.panels.messages', 'messages')
    pass
