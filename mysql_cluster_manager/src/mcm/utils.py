"""This file contains the utils of the cluster manager"""

from datetime import datetime

class Utils:
    """
    Utilities for the project
    """

    @staticmethod
    def is_refresh_needed(last_execution, max_timedelta):
        """
        Is a new execution needed, based on the time delta
        """
        if last_execution is None:
            return True

        return datetime.now() - last_execution > max_timedelta
