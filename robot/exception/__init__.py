__author__ = 'victor'
class ActionExecutionRejection(Exception):
    """Raising this exception will allow other policies
        to predict another action"""

    def __init__(self, action_name, message=None):
        self.action_name = action_name
        self.message = (message or
                        "Custom action '{}' rejected execution of"
                        "".format(action_name))

    def __str__(self):
        return self.message