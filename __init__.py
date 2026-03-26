# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from calibre.customize import InterfaceActionBase

try:
    load_translations()
except NameError:
    pass

class AIVisionMetadataWrapper(InterfaceActionBase):
    name                    = 'AI Vision Metadata'
    description             = _('Automate publication metadata extraction from cover art. Supports cloud APIs and local offline models.')
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'RelUnrelated'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # THIS IS THE MAGIC STRING: 'folder_name.file_name:ClassName'
    actual_plugin           = 'calibre_plugins.ai_vision_metadata.main:AIVisionAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        if self.actual_plugin_:
            from calibre_plugins.ai_vision_metadata.main import ConfigWidget
            return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()