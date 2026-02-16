from PyQt6.QtWidgets import QTableWidgetItem
from datetime import date, datetime

class SortableTableWidgetItem(QTableWidgetItem):
    """
    Custom QTableWidgetItem that uses a dedicated sort_value for comparisons.
    Supports floats, dates, and strings.
    """
    def __init__(self, text, sort_value=None):
        super().__init__(str(text))
        # If no sort_value is provided, use the text itself
        self.sort_value = sort_value if sort_value is not None else text

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
            
        # Get sort value from the other item if it's also a SortableTableWidgetItem
        if hasattr(other, 'sort_value'):
            v2 = other.sort_value
        else:
            # Fallback for standard items: try to parse as float or date if possible, otherwise string
            v2 = other.text()
            
        v1 = self.sort_value
        
        # Handle cases where types are different (e.g. comparing float with None or string)
        try:
            return v1 < v2
        except TypeError:
            # Fallback to string comparison if types are incompatible
            return str(v1) < str(v2)
