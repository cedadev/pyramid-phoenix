from datetime import datetime, timedelta
from pyramid_layout.panel import panel_config

from phoenix.security import Guest

import logging
logger = logging.getLogger(__name__)


@panel_config(name='dashboard_overview', renderer='phoenix:dashboard/templates/dashboard/panels/overview.pt')
def dashboard_overview(context, request):
    return dict(people=len(list(request.db.users)),
                jobs=len(list(request.db.jobs)),
                wps=len(request.catalog.get_services()))


@panel_config(name='dashboard_people', renderer='phoenix:dashboard/templates/dashboard/panels/people.pt')
def dashboard_people(context, request):
    stats = dict(total=len(list(request.db.users)))
    stats['not_activated'] = len(list(request.db.users.find({"group": Guest})))

    d = datetime.now() - timedelta(hours=24)
    stats['logged_in_today'] = len(list(request.db.users.find({"last_login": {"$gt": d}})))

    d = datetime.now() - timedelta(days=7)
    stats['logged_in_this_week'] = len(list(request.db.users.find({"last_login": {"$gt": d}})))
    return stats


@panel_config(name='dashboard_jobs', renderer='phoenix:dashboard/templates/dashboard/panels/jobs.pt')
def dashboard_jobs(context, request):
    return dict(total=len(list(request.db.jobs)),
                running=len(list(request.db.jobs.find(
                {"status": {'$in': ['ProcessAccepted', 'ProcessPaused', 'ProcessStarted']}}))),
                failed=len(list(request.db.jobs.find({"status": "ProcessFailed"}))),
                succeeded=len(list(request.db.jobs.find({"status": "ProcessSucceeded"}))))
