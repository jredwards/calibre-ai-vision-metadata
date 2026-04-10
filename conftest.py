# conftest.py — loaded by pytest before any package __init__.py is imported.
# Stubs out the Calibre and Qt runtime modules so that the plugin's __init__.py
# (which contains `from calibre.customize import InterfaceActionBase`) can be
# imported without a full Calibre installation.
import sys
from types import ModuleType


def _stub(name):
    """Create and register a minimal stub module, plus all its parent modules."""
    parts = name.split('.')
    for i in range(1, len(parts) + 1):
        partial = '.'.join(parts[:i])
        if partial not in sys.modules:
            sys.modules[partial] = ModuleType(partial)


# Calibre runtime modules referenced by __init__.py and main.py
_CALIBRE_STUBS = [
    'calibre',
    'calibre.customize',
    'calibre.gui2',
    'calibre.gui2.actions',
    'calibre.gui2.threaded_jobs',
    'calibre.ebooks',
    'calibre.ebooks.metadata',
    'calibre.utils',
    'calibre.utils.config',
    'calibre_plugins',
    'calibre_plugins.ai_vision_metadata',
    'calibre_plugins.ai_vision_metadata.config',
    'qt',
    'qt.core',
]

for _name in _CALIBRE_STUBS:
    _stub(_name)

# Provide the specific attributes that __init__.py and main.py pull off these stubs
import types

_calibre_customize = sys.modules['calibre.customize']
_calibre_customize.InterfaceActionBase = type('InterfaceActionBase', (), {})

_calibre_gui2 = sys.modules['calibre.gui2']
_calibre_gui2.error_dialog = lambda *a, **kw: None

_calibre_gui2_actions = sys.modules['calibre.gui2.actions']
_calibre_gui2_actions.InterfaceAction = type('InterfaceAction', (), {})

_calibre_gui2_jobs = sys.modules['calibre.gui2.threaded_jobs']
_calibre_gui2_jobs.ThreadedJob = type('ThreadedJob', (), {})

_calibre_utils_config = sys.modules['calibre.utils.config']
_calibre_utils_config.JSONConfig = type('JSONConfig', (), {})

# Qt stub — main.py does `from qt.core import QWidget, ...`
# We only need the stub to not crash; none of Qt is used by helpers.py
_qt_core = sys.modules['qt.core']
for _attr in [
    'QWidget', 'QVBoxLayout', 'QHBoxLayout', 'QGridLayout', 'QLabel',
    'QLineEdit', 'QComboBox', 'QPushButton', 'QMessageBox', 'QIcon',
    'QPixmap', 'pyqtSignal', 'Qt', 'QObject', 'QSpinBox', 'QMenu',
    'QTextEdit', 'QCheckBox',
]:
    setattr(_qt_core, _attr, type(_attr, (), {}))

# calibre_plugins.ai_vision_metadata.config — prefs object used by main.py
_plugin_config = sys.modules['calibre_plugins.ai_vision_metadata.config']
_plugin_config.prefs = {}

# Calibre injects `_()` as a builtin translation function at runtime.
# Install a no-op version so plugin files that use _('...') don't crash.
import builtins
builtins._ = lambda s: s
builtins.load_translations = lambda: None
