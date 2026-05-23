"""In-tree plugin packages.

Importing this module triggers each subpackage's import, which registers
the plugin against ``app.core.plugins.registry``.
"""

# Trigger plugin registration as import side-effects.
from app.plugins import active_recall as active_recall
from app.plugins import notion as notion
