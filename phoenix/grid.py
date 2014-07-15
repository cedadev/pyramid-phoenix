import logging
logger = logging.getLogger(__name__)

from webhelpers.html.builder import HTML
from webhelpers.html.grid import Grid

class UsersGrid(Grid):
    """A generated table for the todo list that supports ordering of
    the task name and due date columns. We also customize the init so
    that we accept the selected_tag and user_tz.
    """

    def __init__(self, request, *args, **kwargs):
        self.request = request
        if 'url' not in kwargs:
            kwargs['url'] = request.current_route_url
        super(UsersGrid, self).__init__(*args, **kwargs)
        self.exclude_ordering = ['_numbered']

    def default_header_column_format(self, column_number, column_name,
        header_label):
        """Override of the ObjectGrid to use <th> for header columns
        """
        if column_name == "_numbered":
            column_name = "numbered"
        if column_name in self.exclude_ordering:
            class_name = "c%s %s" % (column_number, column_name)
            return HTML.tag("th", header_label, class_=class_name)
        else:
            header_label = HTML(
                header_label, HTML.tag("span", class_="marker"))
            class_name = "c%s ordering %s" % (column_number, column_name)
            return HTML.tag("th", header_label, class_=class_name)

    ## def default_header_ordered_column_format(self, column_number, column_name,
    ##                                          header_label):
    ##     """Override of the ObjectGrid to use <th> and to add an icon
    ##     that represents the sort order for the column.
    ##     """
    ##     icon_direction = self.order_dir == 'asc' and 'up' or 'down'
    ##     icon_class = 'icon-chevron-%s' % icon_direction
    ##     icon_tag = HTML.tag("i", class_=icon_class)
    ##     header_label = HTML(header_label, " ", icon_tag)
    ##     if column_name == "_numbered":
    ##         column_name = "numbered"
    ##     class_name = "c%s ordering %s %s" % (
    ##         column_number, self.order_dir, column_name)
    ##     return HTML.tag("th", header_label, class_=class_name)
        

    def __html__(self):
        """Override of the ObjectGrid to use a <thead> so that bootstrap
        renders the styles correctly
        """
        records = []
        # first render headers record
        headers = self.make_headers()
        r = self.default_header_record_format(headers)
        # Wrap the headers in a thead
        records.append(HTML.tag('thead', r))
        # now lets render the actual item grid
        for i, record in enumerate(self.itemlist):
            logger.debug('item %s %s', i, record)
            columns = self.make_columns(i, record)
            if hasattr(self, 'custom_record_format'):
                r = self.custom_record_format(i + 1, record, columns)
            else:
                r = self.default_record_format(i + 1, record, columns)
            records.append(r)
        return HTML(*records)
