from nose.tools import ok_, with_setup
from nose import SkipTest
from nose.plugins.attrib import attr

import __init__ as base

from phoenix import wps
from owslib.wps import monitorExecution

NODES = None

def setup_nodes():
    global NODES
    
    source = dict(
        service = base.SERVICE,
        identifier = "org.malleefowl.storage.testfiles.source",
        input = [],
        output = ['output'],
        sources = [['test1.nc'], ['test2.nc']]
        )
    worker = dict(
        service = base.SERVICE,
        identifier = "de.dkrz.cdo.sinfo.worker",
        input = [],
        output = ['output'])
    NODES = dict(source=source, worker=worker)

@attr('online')
def test_get_wps():
    my_wps = wps.get_wps(base.SERVICE)
    ok_(my_wps != None, base.SERVICE)

@attr('online')
@with_setup(setup_nodes)
def test_execute_restflow():
    global NODES

    my_wps = wps.get_wps(base.SERVICE)
    
    execution = wps.execute_restflow(my_wps, NODES)
    monitorExecution(execution, sleepSecs=1)
    result = execution.processOutputs[0].reference
    ok_('wpsoutputs' in result, result)

