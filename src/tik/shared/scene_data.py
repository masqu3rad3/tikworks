"""Generic module to hold, edit and query data to/from a Maya Node's attribute.

It inherits Python's dict class and overrides the __setitem__ and __getitem__ methods to
store and retrieve data from a Maya node's attribute.
"""

import ast
import logging
from collections import UserDict
import tik.maya as tm

LOG = logging.getLogger(__name__)

class SceneDictionary(UserDict):
    def __init__(self, node, attribute="sceneData"):
        super(SceneDictionary, self).__init__()
        self.node = tm.resolve(node)
        self.attribute = attribute

    def __setitem__(self, key, value):
        """Set the data on the node."""
        if not self.node.exists():
            LOG.error("Node {} doesn't exist".format(self.node.name))
            return False
        super(SceneDictionary, self).__setitem__(key, value)

        self.validate_attribute()
        self.node[self.attribute].set(str(self))

    def __getitem__(self, key):
        """Retrieve the data from the scene node."""
        if not self.node.exists():
            _data = None
        else:
            self.validate_attribute()
            _all_data = self.node[self.attribute].get(str(self)) or "{}"
            _data = ast.literal_eval(_all_data).get(key, None)
        # first ingest the data to the dict
        if _data:
            super(SceneDictionary, self).__setitem__(key, _data)
        # now run the original function with the new data
        return super(SceneDictionary, self).__getitem__(key)\

    def validate_attribute(self):
        """Create the attribute on the node."""
        if not self.node.has_attr(self.attribute):
            self.node.add_attr(self.attribute, dataType="string")
