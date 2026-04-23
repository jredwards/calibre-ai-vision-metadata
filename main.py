# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
import base64
import json
import urllib.request
import datetime
import os
from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                     QComboBox, QPushButton, QMessageBox, QIcon, QPixmap,
                     pyqtSignal, Qt, QObject, QSpinBox, QMenu, QTextEdit, QCheckBox)

from calibre.gui2 import error_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre_plugins.ai_vision_metadata.config import prefs
from calibre_plugins.ai_vision_metadata.helpers import (
    ALL_FIELDS, ALL_FIELD_KEYS, FIELD_GROUPS,
    is_null_value, strip_null_values,
    clean_title, clean_author_name, clean_publisher,
    verify_with_google_books,
    build_approved_data,
)

try:
    load_translations()
except NameError:
    pass

class WorkerSignals(QObject):
    review_signal = pyqtSignal(object, object, object)
    error_signal = pyqtSignal(str)  

DEFAULT_PROMPT = (
    "Analyze this book cover image. "
    "Return ONLY a JSON object with exactly these four keys: "
    "'title' (string: the full book title exactly as printed on the cover), "
    "'creators' (list of strings: every author, editor, or illustrator name printed on the cover, "
    "in the order they appear — return an empty list if none are visible), "
    "'publisher' (string: the publisher name if clearly printed on the cover, otherwise null), "
    "'languages' (list of strings: 3-letter ISO 639-2 language codes for the language of the text "
    "on the cover, e.g. ['eng'] for English, ['fra'] for French). "
    "Do not include any other keys. "
    "If a field cannot be determined from the cover, return null for that field. "
    "Do not guess, infer, or use web search."
)

class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.l = QVBoxLayout()
        self.setLayout(self.l)
        
        # --- 1. Provider Selection ---
        self.label_provider = QLabel(_('AI Provider:'))
        self.l.addWidget(self.label_provider)
        
        self.provider_combo = QComboBox(self)
        self.providers = ['Google Gemini', 'OpenAI', 'Anthropic', 'Local (Ollama/LM Studio)']
        self.provider_combo.addItems(self.providers)
        
        # --- Load saved provider, defaulting to Google ---
        saved_provider = prefs.get('ai_provider', 'Google Gemini')
        self.provider_combo.setCurrentText(saved_provider)
        self.provider_combo.currentIndexChanged.connect(self.toggle_provider_fields)
        self.l.addWidget(self.provider_combo)

        # --- Dynamic Helper Link Label ---
        self.link_label = QLabel()
        self.link_label.setOpenExternalLinks(True)
        self.l.addWidget(self.link_label)
        
        # --- 2. API Key Fields (Dedicated Memory Banks) ---
        self.label_key = QLabel(_('API Key:'))
        self.l.addWidget(self.label_key)
        
        # Google Key (Falls back to the old agnostic key so you don't lose it)
        self.key_google = QLineEdit(self)
        self.key_google.setText(prefs.get('api_key_google', prefs.get('api_key', '')))
        self.l.addWidget(self.key_google)
        
        # OpenAI Key
        self.key_openai = QLineEdit(self)
        self.key_openai.setText(prefs.get('api_key_openai', ''))
        self.l.addWidget(self.key_openai)
        
        # Anthropic Key
        self.key_anthropic = QLineEdit(self)
        self.key_anthropic.setText(prefs.get('api_key_anthropic', ''))
        self.l.addWidget(self.key_anthropic)
        
        # --- 3. Local Base URL Field ---
        self.label_url = QLabel(_('Local Base URL (e.g., http://localhost:11434):'))
        self.l.addWidget(self.label_url)
        self.url_input = QLineEdit(self)
        self.url_input.setText(prefs.get('local_url', 'http://localhost:11434'))
        self.l.addWidget(self.url_input)
        
        # --- 4. Model Selection Area (Dedicated Memory Banks) ---
        self.label_model = QLabel(_('Model Name:'))
        self.l.addWidget(self.label_model)
        self.model_layout = QHBoxLayout()
        
        # Google Model
        self.model_google = QComboBox(self)
        self.model_google.setEditable(True)
        # Fallback to the legacy 'model_name' so you don't lose your current setting
        saved_google = prefs.get('model_google', prefs.get('model_name', 'gemini-2.5-pro'))
        self.model_google.addItem(saved_google)
        self.model_google.setCurrentText(saved_google)
        self.model_layout.addWidget(self.model_google)
        
        # OpenAI Model
        self.model_openai = QComboBox(self)
        self.model_openai.setEditable(True)
        saved_openai = prefs.get('model_openai', 'gpt-4o')
        self.model_openai.addItem(saved_openai)
        self.model_openai.setCurrentText(saved_openai)
        self.model_layout.addWidget(self.model_openai)
        
        # Anthropic Model
        self.model_anthropic = QComboBox(self)
        self.model_anthropic.setEditable(True)
        saved_anthropic = prefs.get('model_anthropic', 'claude-3-7-sonnet-latest')
        self.model_anthropic.addItem(saved_anthropic)
        self.model_anthropic.setCurrentText(saved_anthropic)
        self.model_layout.addWidget(self.model_anthropic)
        
        # Local Model
        self.model_local = QComboBox(self)
        self.model_local.setEditable(True)
        saved_local = prefs.get('model_local', 'llava')
        self.model_local.addItem(saved_local)
        self.model_local.setCurrentText(saved_local)
        self.model_layout.addWidget(self.model_local)
        
        self.fetch_button = QPushButton(_("Fetch Available Models"), self)
        self.fetch_button.clicked.connect(self.fetch_models)
        self.model_layout.addWidget(self.fetch_button)
        
        self.l.addLayout(self.model_layout)

        # --- 5. Timeout Configuration ---
        self.label_timeout = QLabel(_('Network Timeout (seconds):'))
        self.l.addWidget(self.label_timeout)

        self.timeout_spin = QSpinBox(self)
        self.timeout_spin.setRange(30, 86400)
        self.timeout_spin.setValue(int(prefs.get('timeout', 120)))
        self.l.addWidget(self.timeout_spin)

        self.label_delay = QLabel(_('Delay Between Batch Requests (seconds):'))
        self.l.addWidget(self.label_delay)

        self.delay_spin = QSpinBox(self)
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setValue(int(prefs.get('batch_delay', 2)))
        self.l.addWidget(self.delay_spin)

        self.label_books_key = QLabel(_(
            'Google Books API Key (optional — raises rate limit; leave blank to use unauthenticated):'))
        self.l.addWidget(self.label_books_key)

        self.key_google_books = QLineEdit(self)
        self.key_google_books.setPlaceholderText(_('Leave blank for unauthenticated access'))
        self.key_google_books.setText(prefs.get('api_key_google_books', ''))
        self.l.addWidget(self.key_google_books)

        # --- 6. Default Fields to Update ---
        self.l.addWidget(QLabel(_('<b>Fields to Update</b>')))
        self.l.addWidget(QLabel(_(
            '<i>Fields are grouped by their data source. Uncheck any field to prevent the '
            'plugin from ever writing to it. "Manual entry only" fields never auto-populate — '
            'they appear in the single-book review dialog for optional manual input.</i>'
        )))

        enabled_fields = prefs.get('enabled_fields', ALL_FIELD_KEYS)
        self.field_checkboxes = {}
        field_labels = dict(ALL_FIELDS)

        for group_label, keys in FIELD_GROUPS:
            header = QLabel(_(f'<b>{group_label}:</b>'))
            header.setWordWrap(True)
            header.setContentsMargins(0, 8, 0, 2)
            self.l.addWidget(header)

            group_widget = QWidget()
            group_grid = QGridLayout(group_widget)
            group_grid.setContentsMargins(12, 0, 0, 0)
            group_grid.setHorizontalSpacing(20)

            for i, key in enumerate(keys):
                chk = QCheckBox(_(field_labels[key]))
                chk.setChecked(key in enabled_fields)
                group_grid.addWidget(chk, i // 3, i % 3)
                self.field_checkboxes[key] = chk

            self.l.addWidget(group_widget)

        # --- 7. Prompt Tuning Area (Dedicated Memory Banks) ---
        self.prompt_layout = QHBoxLayout()
        self.label_prompt = QLabel(_('System Prompt (Advanced):'))
        
        self.reset_prompt_btn = QPushButton(_("Restore Default"), self)
        self.reset_prompt_btn.clicked.connect(self.restore_default_prompt)
        
        self.prompt_layout.addWidget(self.label_prompt)
        self.prompt_layout.addStretch()
        self.prompt_layout.addWidget(self.reset_prompt_btn)
        self.l.addLayout(self.prompt_layout)
        
        # Google Prompt
        self.prompt_google = QTextEdit(self)
        self.prompt_google.setAcceptRichText(False)
        self.prompt_google.setMinimumHeight(150)
        self.prompt_google.setPlainText(prefs.get('prompt_google', prefs.get('custom_prompt', DEFAULT_PROMPT)))
        self.l.addWidget(self.prompt_google)
        
        # OpenAI Prompt
        self.prompt_openai = QTextEdit(self)
        self.prompt_openai.setAcceptRichText(False)
        self.prompt_openai.setMinimumHeight(150)
        self.prompt_openai.setPlainText(prefs.get('prompt_openai', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_openai)
        
        # Anthropic Prompt
        self.prompt_anthropic = QTextEdit(self)
        self.prompt_anthropic.setAcceptRichText(False)
        self.prompt_anthropic.setMinimumHeight(150)
        self.prompt_anthropic.setPlainText(prefs.get('prompt_anthropic', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_anthropic)
        
        # Local Prompt
        self.prompt_local = QTextEdit(self)
        self.prompt_local.setAcceptRichText(False)
        self.prompt_local.setMinimumHeight(150)
        self.prompt_local.setPlainText(prefs.get('prompt_local', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_local)

        # --- INITIALIZATION ---
        # Run the toggle function once right now so the UI initializes in the correct state
        self.toggle_provider_fields()

    def toggle_provider_fields(self):
        """Dynamically shows/hides inputs based on the selected provider."""
        provider = self.provider_combo.currentText()
        
        # Hide all key inputs first to reset the board
        self.key_google.setVisible(False)
        self.key_openai.setVisible(False)
        self.key_anthropic.setVisible(False)
        # Hide all model combos first
        self.model_google.setVisible(False)
        self.model_openai.setVisible(False)
        self.model_anthropic.setVisible(False)
        self.model_local.setVisible(False)        
        # Hide all prompt editing areas first
        self.prompt_google.setVisible(False)
        self.prompt_openai.setVisible(False)
        self.prompt_anthropic.setVisible(False)
        self.prompt_local.setVisible(False)
        
        if provider == 'Local (Ollama/LM Studio)':
            self.link_label.setText(_("Get Local Tools:") + ' <a href="https://ollama.com/download">Ollama</a> | <a href="https://lmstudio.ai/">LM Studio</a>')
            self.label_key.setVisible(False)
            self.label_url.setVisible(True)
            self.url_input.setVisible(True)
            self.model_local.setVisible(True)
            self.prompt_local.setVisible(True)
        else:
            self.label_key.setVisible(True)
            self.label_url.setVisible(False)
            self.url_input.setVisible(False)
            
            if provider == 'Google Gemini':
                self.link_label.setText('<a href="https://aistudio.google.com/app/apikey">' + _("Get Google API Key") + '</a>')
                self.key_google.setVisible(True)
                self.model_google.setVisible(True)
                self.prompt_google.setVisible(True)
            elif provider == 'OpenAI':
                self.link_label.setText('<a href="https://platform.openai.com/api-keys">' + _("Get OpenAI API Key") + '</a>')
                self.key_openai.setVisible(True)
                self.model_openai.setVisible(True)
                self.prompt_openai.setVisible(True)
            elif provider == 'Anthropic':
                self.link_label.setText('<a href="https://console.anthropic.com/settings/keys">' + _("Get Anthropic API Key") + '</a>')
                self.key_anthropic.setVisible(True)
                self.model_anthropic.setVisible(True)
                self.prompt_anthropic.setVisible(True)

    def fetch_models(self):
        provider = self.provider_combo.currentText()
        local_url = self.url_input.text().strip().rstrip('/')
        
        # --- 1. Identify the Active Key and Dropdown ---
        if provider == 'Google Gemini':
            api_key = self.key_google.text().strip()
            active_combo = self.model_google
        elif provider == 'OpenAI':
            api_key = self.key_openai.text().strip()
            active_combo = self.model_openai
        elif provider == 'Anthropic':
            api_key = self.key_anthropic.text().strip()
            active_combo = self.model_anthropic
        else:
            api_key = "" 
            active_combo = self.model_local
            
        # --- 2. Validation ---
        if provider != 'Local (Ollama/LM Studio)' and not api_key:
            QMessageBox.warning(self, _("Missing Key"), _("Please enter your API key for {0}.").format(provider))
            return
            
        if provider == 'Local (Ollama/LM Studio)' and not local_url:
            QMessageBox.warning(self, _("Missing URL"), _("Please enter your local server's Base URL."))
            return
            
        # Clear ONLY the currently visible dropdown
        active_combo.clear()
        
        # --- 3. API Routing & Populating ---
        try:
            if provider == 'Google Gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                exclusion_list = ['gemini-2.0-flash', 'gemini-2.0-pro', 'gemini-1.0-pro']
                for model in data.get('models', []):
                    if 'generateContent' in model.get('supportedGenerationMethods', []):
                        model_id = model.get('name', '').replace('models/', '')
                        if model_id not in exclusion_list:
                            active_combo.addItem(model_id)
                            
            elif provider == 'OpenAI':
                url = "https://api.openai.com/v1/models"
                req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                for model in data.get('data', []):
                    model_id = model.get('id', '')
                    if 'gpt-4o' in model_id or 'gpt-4-turbo' in model_id:
                        active_combo.addItem(model_id)
                        
            elif provider == 'Anthropic':
                anthropic_models = [
                    'claude-3-7-sonnet-latest',
                    'claude-3-5-sonnet-latest', 
                    'claude-3-5-haiku-latest',
                    'claude-3-opus-latest'
                ]
                active_combo.addItems(anthropic_models)
                
            elif provider == 'Local (Ollama/LM Studio)':
                url = f"{local_url}/v1/models"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    
                for model in data.get('data', []):
                    active_combo.addItem(model.get('id', ''))
                    
            QMessageBox.information(self, _("Success"), _("Models refreshed successfully!"))
            
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to fetch models: {0}").format(str(e)))

    def restore_default_prompt(self):
        reply = QMessageBox.question(self, _('Restore Default'), 
                                     _('Are you sure you want to overwrite your custom prompt with the default instructions?'),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            provider = self.provider_combo.currentText()
            if provider == 'Google Gemini':
                self.prompt_google.setPlainText(DEFAULT_PROMPT)
            elif provider == 'OpenAI':
                self.prompt_openai.setPlainText(DEFAULT_PROMPT)
            elif provider == 'Anthropic':
                self.prompt_anthropic.setPlainText(DEFAULT_PROMPT)
            elif provider == 'Local (Ollama/LM Studio)':
                self.prompt_local.setPlainText(DEFAULT_PROMPT)

    def save_settings(self):
        # 1. Save the active provider
        prefs['ai_provider'] = self.provider_combo.currentText()
        
        # 2. Save API Keys & URLs
        prefs['api_key_google'] = self.key_google.text().strip()
        prefs['api_key_openai'] = self.key_openai.text().strip()
        prefs['api_key_anthropic'] = self.key_anthropic.text().strip()
        prefs['local_url'] = self.url_input.text().strip()
        
        # 3. Save Models
        prefs['model_google'] = self.model_google.currentText().strip()
        prefs['model_openai'] = self.model_openai.currentText().strip()
        prefs['model_anthropic'] = self.model_anthropic.currentText().strip()
        prefs['model_local'] = self.model_local.currentText().strip()
        
        # 4. Save Custom Prompts
        prefs['prompt_google'] = self.prompt_google.toPlainText().strip()
        prefs['prompt_openai'] = self.prompt_openai.toPlainText().strip()
        prefs['prompt_anthropic'] = self.prompt_anthropic.toPlainText().strip()
        prefs['prompt_local'] = self.prompt_local.toPlainText().strip()
        
        # 5. Save General Settings
        prefs['timeout'] = self.timeout_spin.value()
        prefs['batch_delay'] = self.delay_spin.value()
        prefs['api_key_google_books'] = self.key_google_books.text().strip()

        # 6. Save enabled fields
        prefs['enabled_fields'] = [key for key, _ in ALL_FIELDS if self.field_checkboxes[key].isChecked()]

class AIVisionAction(InterfaceAction):
    name = 'AI Vision Metadata' # DO NOT TRANSLATE
    action_spec = ('AI Vision Metadata', 'images/icon.png', _('Identify book via AI Vision'), 'Ctrl+Shift+I')

    def genesis(self):
        self.signals = WorkerSignals()
        self.signals.review_signal.connect(self._show_review_dialog, type=Qt.ConnectionType.QueuedConnection)
        
        # --- Wire up the error signal using a QueuedConnection ---
        self.signals.error_signal.connect(self._show_error_dialog, type=Qt.ConnectionType.QueuedConnection)
        # --------------------------------------------------------------

        # 1. The Main Action (This still catches the direct toolbar click)
        self.qaction.triggered.connect(self.identify_book)
        
        # --- Dropdown Menu for Configuration & Context Menu ---
        self.menu = QMenu(self.gui)
        
        # 2. Add the primary action INTO the menu for right-click users
        self.run_action = self.create_action(
            spec=(_('Identify Cover'), 'images/icon.png', _('Run AI Vision Metadata on selected book'), None),
            attr='run_action'
        )

        self.run_action.triggered.connect(self.identify_book)
        self.menu.addAction(self.run_action)
        
        # Add a visual separator line
        self.menu.addSeparator()
        
        # 3. Add the configuration sub-action
        self.config_action = self.create_action(
            spec=('Configure AI Vision', 'images/config.png', 'Settings for AI Vision Metadata', None),
            attr='config_action'
        )
        self.config_action.triggered.connect(self.show_configuration)
        self.menu.addAction(self.config_action)
        
        self.qaction.setMenu(self.menu)
        # ------------------------------------------------------
        
        try:
            # Ask the resource manager to extract both images from the zip
            resources = self.load_resources(['images/icon.png', 'images/config.png'])
            
            # 1. Apply the main icon to the toolbar button and the "Identify Cover" menu item
            icon_data = resources.get('images/icon.png')
            if icon_data:
                pixmap = QPixmap()
                pixmap.loadFromData(icon_data)
                main_icon = QIcon(pixmap)
                self.qaction.setIcon(main_icon)
                self.run_action.setIcon(main_icon)
                
            # 2. Apply the custom config icon to the settings menu item
            config_data = resources.get('images/config.png')
            if config_data:
                config_pixmap = QPixmap()
                config_pixmap.loadFromData(config_data)
                self.config_action.setIcon(QIcon(config_pixmap))
                
        except Exception as e:
            # Fails silently if the images aren't found, falling back to default text/icons
            pass

    def show_configuration(self):
        # This native Calibre command instantly summons the ConfigWidget
        self.interface_action_base_plugin.do_user_config(self.gui)

    def identify_book(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            from calibre.gui2 import error_dialog
            return error_dialog(self.gui, _('No Selection'), _('Please select at least one book.'), show=True)

        book_count = len(rows)
        self.batch_queue = [self.gui.library_view.model().id(row) for row in rows]

        if book_count > 1:
            # Ask for permission before running unattended on multiple books
            enabled_fields = prefs.get('enabled_fields', ALL_FIELD_KEYS)
            field_labels = [label for key, label in ALL_FIELDS if key in enabled_fields]
            field_list = ', '.join(field_labels) if field_labels else _('(none — check your settings)')

            from calibre.gui2 import question_dialog
            confirmed = question_dialog(
                self.gui,
                _('Batch Process {0} Books?').format(book_count),
                _('<p>You have selected <b>{0} books</b>.</p>'
                  '<p>The AI will process each cover and automatically apply the following '
                  'fields without asking you to review each one:</p>'
                  '<p><b>{1}</b></p>'
                  '<p>Proceed?</p>').format(book_count, field_list),
                default_yes=False
            )
            if not confirmed:
                return
            self.batch_auto_apply = True
            self._batch_log = []  # [{'title', 'fields', 'status', 'error'}]
        else:
            self.batch_auto_apply = False
            self._batch_log = []

        # Start the assembly line
        self.process_next_in_queue()

    def process_next_in_queue(self):
        """Pops the next book from the queue and starts the AI job."""
        if not hasattr(self, 'batch_queue') or not self.batch_queue:
            if getattr(self, 'batch_auto_apply', False) and getattr(self, '_batch_log', []):
                self._show_batch_summary()
            return

        # Apply inter-request delay for batch runs (skip for the very first book)
        if getattr(self, 'batch_auto_apply', False) and hasattr(self, '_batch_log'):
            delay = int(prefs.get('batch_delay', 2))
            if delay > 0:
                import time
                time.sleep(delay)

        book_id = self.batch_queue.pop(0)
        db = self.gui.current_db.new_api

        # Fetch the cover path
        rel_path = db.field_for('path', book_id)
        if rel_path:
            lib_path = self.gui.current_db.library_path
            cover_path = os.path.join(lib_path, rel_path.replace('/', os.sep), 'cover.jpg')
        else:
            cover_path = None

        if not cover_path or not os.path.exists(cover_path):
            # If there's no cover, show an error for this book and immediately grab the next one!
            self.signals.error_signal.emit(_("Book ID {0} has no cover image to process. Skipping to next.").format(book_id))
            self.process_next_in_queue()
            return

        # Launch the background thread
        from calibre.gui2.threaded_jobs import ThreadedJob
        job = ThreadedJob(
            'identifying_book', 
            _('Analyzing cover for book ID: {0}').format(book_id),  
            self.run_api_request, 
            (book_id, cover_path, ""), # Passing "" since api_key_ignored is no longer used
            {}, 
            self.job_finished
        )
        self.gui.job_manager.run_threaded_job(job)

    def run_api_request(self, book_id, cover_path, api_key_ignored, **kwargs):
        import time
        start_time = time.time() # --- Start the clock ---

        with open(cover_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')

        provider = prefs.get('ai_provider', 'Google Gemini')
        local_url = prefs.get('local_url', 'http://localhost:11434').rstrip('/')
        
        # --- Master Variable Router ---
        if provider == 'Google Gemini':
            api_key = prefs.get('api_key_google', prefs.get('api_key', ''))
            model_name = prefs.get('model_google', prefs.get('model_name', 'gemini-2.5-pro'))
            prompt = prefs.get('prompt_google', DEFAULT_PROMPT)
        elif provider == 'OpenAI':
            api_key = prefs.get('api_key_openai', '')
            model_name = prefs.get('model_openai', 'gpt-4o')
            prompt = prefs.get('prompt_openai', DEFAULT_PROMPT)
        elif provider == 'Anthropic':
            api_key = prefs.get('api_key_anthropic', '')
            model_name = prefs.get('model_anthropic', 'claude-3-7-sonnet-latest')
            prompt = prefs.get('prompt_anthropic', DEFAULT_PROMPT)
        else:
            api_key = ""
            model_name = prefs.get('model_local', 'llava')
            prompt = prefs.get('prompt_local', DEFAULT_PROMPT)
            
        if not prompt: 
            prompt = DEFAULT_PROMPT
        # -----------------------------------

        # --- DYNAMIC ROUTING & PAYLOAD BUILDER ---
        headers = {'Content-Type': 'application/json'}

        if provider == 'Google Gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}
                    ]
                }],
                "tools": [{"googleSearch": {}}]
            }

        elif provider in ['OpenAI', 'Local (Ollama/LM Studio)']:
            if provider == 'OpenAI':
                url = "https://api.openai.com/v1/chat/completions"
                headers['Authorization'] = f'Bearer {api_key}'
            else:
                url = f"{local_url}/v1/chat/completions"

            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
                        ]
                    }
                ],
                # This explicitly tells OpenAI/Ollama to format their output as JSON
                "response_format": {"type": "json_object"} 
            }

        elif provider == 'Anthropic':
            url = "https://api.anthropic.com/v1/messages"
            headers['x-api-key'] = api_key
            headers['anthropic-version'] = '2023-06-01'

            payload = {
                "model": model_name,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_data
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            }
        else:
             return {"error_msg": _("Unknown AI Provider selected.")}

        import urllib.error
        
        # Fetch the user-defined timeout, defaulting to 120 if not found
        timeout_val = int(prefs.get('timeout', 120))
        
        try:
            data = json.dumps(payload).encode('utf-8')
            # --- Pass the dynamic 'headers' variable instead of a hardcoded dictionary ---
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            # -----------------------------------------------------------------------------

            try:
                # Pass the dynamic timeout variable to the request
                with urllib.request.urlopen(req, timeout=timeout_val) as response:
                    res_json = json.loads(response.read().decode('utf-8'))
                    
            except urllib.error.HTTPError as http_err:
                error_body = http_err.read().decode('utf-8')
                try:
                    # Attempt to parse the JSON error response
                    error_json = json.loads(error_body)
                    
                    # Google, OpenAI, and Anthropic all conveniently use this exact nested structure!
                    clean_msg = error_json.get('error', {}).get('message', error_body)
                    
                    # --- Dynamically inject the provider name ---
                    return {"error_msg": _("{0} API Error ({1}): {2}").format(provider, http_err.code, clean_msg)}
                    # --------------------------------------------
                    
                except json.JSONDecodeError:
                    # Fallback just in case the server sends a plain HTML error page
                    return {"error_msg": _("{0} API Error (HTTP {1}): {2}").format(provider, http_err.code, error_body)}

            except TimeoutError:
                return {"error_msg": _("Request timed out after {0}s. The AI API did not respond in time.").format(timeout_val)}
            except urllib.error.URLError as url_err:
                return {"error_msg": _("Network connection failed: {0}").format(url_err.reason)}
            except Exception as e:
                return {"error_msg": _("An unexpected error occurred: {0}").format(str(e))}
            
            # --- UNIFIED RESPONSE PARSER ---
            raw_text = ""
            
            if provider == 'Google Gemini':
                candidate = res_json.get('candidates', [{}])[0]
                if candidate.get('finishReason') == 'SAFETY':
                    return {"error_msg": _("The AI blocked this cover due to its safety filters.")}
                parts = candidate.get('content', {}).get('parts', [])
                if parts:
                    raw_text = parts[0].get('text', '')

            elif provider in ['OpenAI', 'Local (Ollama/LM Studio)']:
                choices = res_json.get('choices', [])
                if choices:
                    raw_text = choices[0].get('message', {}).get('content', '')

            elif provider == 'Anthropic':
                content_blocks = res_json.get('content', [])
                if content_blocks:
                    raw_text = content_blocks[0].get('text', '')

            if not raw_text:
                return {"error_msg": _("The AI returned an empty response. The model may have failed to process the image.")}
                
            # --- SURGICAL JSON EXTRACTION ---
            import re
            # This looks for everything between the first { and the last }
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            
            if match:
                clean_json = match.group(0)
            else:
                # Fallback just in case it didn't use brackets correctly
                clean_json = raw_text.replace('```json', '').replace('```', '').strip()
                
            try:
                metadata = json.loads(clean_json)

                # --- Strip null/empty values returned by the AI ---
                metadata = strip_null_values(metadata)
                # ---------------------------------------------------

                # --- Normalise languages to a list (AI sometimes returns a bare string) ---
                if isinstance(metadata.get('languages'), str):
                    metadata['languages'] = [metadata['languages']]
                # ---------------------------------------------------------------------------

                # --- Clean up title capitalisation ---
                if isinstance(metadata.get('title'), str):
                    metadata['title'] = clean_title(metadata['title'])
                # ---------------------------------------------------

                # --- Clean up publisher name capitalisation ---
                if isinstance(metadata.get('publisher'), str):
                    metadata['publisher'] = clean_publisher(metadata['publisher'])
                # ---------------------------------------------------

                # --- Clean up author names ---
                raw_creators = metadata.get('creators')
                if raw_creators is not None:
                    names_in = raw_creators if isinstance(raw_creators, list) else [str(raw_creators)]
                    names_out = [clean_author_name(n) for n in names_in if isinstance(n, str)]
                    names_out = [n for n in names_out if n]  # drop rejected names
                    if names_out:
                        metadata['creators'] = names_out
                    else:
                        del metadata['creators']  # all names rejected → omit field
                # ---------------------------------------------------

                # --- Google Books verification and enrichment ---
                if metadata.get('title'):
                    gb_api_key = prefs.get('api_key_google_books', '') or None
                    verification = verify_with_google_books(
                        metadata['title'],
                        metadata.get('creators'),
                        api_key=gb_api_key,
                        publisher=metadata.get('publisher'),
                    )
                    corrections = verification.get('corrections', {})
                    v_status = verification.get('status', 'unverified')
                    # Apply title correction
                    title_fix = corrections.get('title')
                    if title_fix and title_fix.get('to'):
                        metadata['title'] = title_fix['to']
                    # Apply author correction
                    author_fix = corrections.get('authors')
                    if author_fix and author_fix.get('to'):
                        corrected = clean_author_name(author_fix['to'])
                        if corrected:
                            metadata['creators'] = [corrected]
                    # Apply enrichment: ISBN always; publisher/pubdate/language only if absent
                    enrichment = verification.get('enrichment', {})
                    enabled_fields = prefs.get('enabled_fields', ALL_FIELD_KEYS)
                    had_publisher = bool(metadata.get('publisher'))
                    had_languages = bool(metadata.get('languages'))
                    provenance = {}
                    if 'identifiers' in enabled_fields and enrichment.get('isbn'):
                        metadata['identifiers'] = f"isbn:{enrichment['isbn']}"
                        provenance['identifiers'] = {'ai': None, 'gb': metadata['identifiers']}
                    if 'publisher' in enabled_fields and enrichment.get('publisher'):
                        ai_publisher = metadata.get('publisher') if had_publisher else None
                        metadata['publisher'] = enrichment['publisher']
                        provenance['publisher'] = {'ai': ai_publisher, 'gb': metadata['publisher']}
                    if 'pubdate' in enabled_fields and enrichment.get('pubdate') and not metadata.get('pub_year'):
                        # publishedDate may be "YYYY", "YYYY-MM", or "YYYY-MM-DD"
                        parts = enrichment['pubdate'].split('-')
                        metadata['pub_year'] = parts[0]
                        if len(parts) >= 2:
                            metadata['pub_month'] = parts[1]
                        if len(parts) >= 3:
                            metadata['pub_day'] = parts[2]
                        provenance['pubdate'] = {'ai': None, 'gb': enrichment['pubdate']}
                    if 'languages' in enabled_fields and enrichment.get('language') and not had_languages:
                        metadata['languages'] = [enrichment['language']]
                        provenance['languages'] = {'ai': None, 'gb': enrichment['language']}
                    # Track AI field provenance: {'ai': raw_value, 'gb': corrected_value}
                    # or {'ai': raw_value, 'gb_status': verification_status}
                    # Note: 'title_only' means the title DID match — only the author didn't.
                    title_gb_status = 'verified' if v_status in ('verified', 'corrected', 'title_only') else v_status
                    if 'title' in metadata:
                        if title_fix:
                            provenance['title'] = {'ai': title_fix['from'], 'gb': metadata['title']}
                        else:
                            provenance['title'] = {'ai': metadata['title'], 'gb_status': title_gb_status}
                    if 'creators' in metadata:
                        creators_display = ', '.join(metadata['creators'])
                        if author_fix and author_fix.get('from') is None:
                            provenance['authors'] = {'ai': None, 'gb': creators_display}
                        elif author_fix:
                            provenance['authors'] = {'ai': author_fix['from'], 'gb': creators_display}
                        else:
                            # 'corrected' means a *title* correction — the author still matched
                            authors_gb_status = ('verified' if v_status in ('verified', 'corrected')
                                                 else v_status)
                            provenance['authors'] = {'ai': creators_display, 'gb_status': authors_gb_status}
                    if had_publisher and 'publisher' not in provenance:
                        provenance['publisher'] = {'ai': metadata['publisher'], 'gb_status': title_gb_status}
                    if 'languages' in metadata and 'languages' not in provenance:
                        langs_display = ', '.join(metadata['languages'])
                        provenance['languages'] = {'ai': langs_display, 'gb_status': title_gb_status}
                    metadata['_provenance'] = provenance
                    metadata['_verification'] = verification
                # -------------------------------------------------

                # --- Inject dynamic provider, model, and duration ---
                elapsed = time.time() - start_time
                metadata['ai_provider'] = provider
                metadata['ai_model_used'] = model_name
                metadata['api_duration'] = round(elapsed, 1) # Rounds to one decimal place
                # ----------------------------------------------------

            except json.JSONDecodeError as e:
                return {"error_msg": _("Data Parsing Error: Could not read AI output.\nRaw Output: {0}...").format(raw_text[:150])}

            # --- Return the cover_path along with the ID and metadata ---
            return (book_id, metadata, cover_path)
            # ------------------------------------------------------------

        except Exception as e:
            return {"error_msg": _("Data Parsing Error: {0}").format(str(e))}

    def job_finished(self, job):
        if job.failed:
            if getattr(self, 'batch_auto_apply', False):
                # In batch mode: log the failure silently and keep the queue moving.
                # Showing a blocking dialog here would stall the batch permanently.
                error_msg = str(getattr(job, 'exception', None) or _('Job failed (unknown error)'))
                try:
                    failed_book_id = str(job.args[0]) if getattr(job, 'args', None) else ''
                except Exception:
                    failed_book_id = ''
                self._batch_log.append({
                    'book_id': failed_book_id,
                    'title': _('Book ID {0}').format(failed_book_id) if failed_book_id else _('Unknown'),
                    'field_data': [], 'status': 'error', 'error': error_msg,
                })
                self.process_next_in_queue()
            else:
                self.gui.job_exception(job, dialog_title=_("AI Vision Failed"))
            return

        result = job.result

        if "error_msg" in result:
            self.signals.error_signal.emit(result["error_msg"])
            return
        else:
            book_id, metadata, cover_path = job.result
            self.signals.review_signal.emit(book_id, metadata, cover_path)
            
    def _build_approved_data(self, metadata, enabled_fields):
        return build_approved_data(metadata, enabled_fields)

    def _show_review_dialog(self, book_id, metadata, cover_path):
        try:
            enabled_fields = prefs.get('enabled_fields', ALL_FIELD_KEYS)

            if getattr(self, 'batch_auto_apply', False):
                approved_data = self._build_approved_data(metadata, enabled_fields)
                # Fetch original Calibre values before overwriting them
                db = self.gui.current_db.new_api
                mi = db.get_metadata(book_id)
                _original = {
                    'title':       mi.title or '',
                    'authors':     ', '.join(mi.authors) if mi.authors else '',
                    'languages':   ', '.join(mi.languages) if mi.languages else '',
                    'publisher':   mi.publisher or '',
                    'pubdate':     (mi.pubdate.strftime('%Y-%m-%d')
                                   if mi.pubdate and getattr(mi.pubdate, 'year', 9999) < 9000 else ''),
                    'identifiers': ', '.join(f"{k}:{v}" for k, v in (mi.identifiers or {}).items()),
                }
                if approved_data:
                    self.apply_metadata(book_id, approved_data)
                provenance = metadata.get('_provenance', {})
                field_data = []
                if approved_data:
                    for field_key, value in approved_data.items():
                        field_label = dict(ALL_FIELDS).get(field_key, field_key)
                        p = provenance.get(field_key, {})
                        ai_str = str(p['ai']) if p.get('ai') else '\u2013'
                        gb      = p.get('gb')
                        gb_stat = p.get('gb_status', '')
                        if p.get('ai') is None and gb:
                            gb_state = 'enriched'
                            gb_str   = str(gb)
                        elif p.get('ai') and gb:
                            gb_state = 'corrected'
                            gb_str   = str(gb)
                        elif gb_stat in ('verified', 'corrected'):
                            gb_state = 'verified'
                            gb_str   = ai_str   # confirmed same value
                        elif gb_stat in ('title_only', 'unverified'):
                            gb_state = 'unverified'
                            gb_str   = _('(unverified)')
                        elif gb_stat == 'rate_limited':
                            gb_state = 'rate_limited'
                            gb_str   = _('(rate limited)')
                        else:
                            gb_state = ''
                            gb_str   = '\u2013'
                        orig_str = _original.get(field_key, '')
                        field_data.append({
                            'field':          field_label,
                            'original_value': orig_str,
                            'ai_value':       ai_str,
                            'gb_value':       gb_str,
                            'gb_state':       gb_state,
                        })
                self._batch_log.append({
                    'book_id': str(book_id),
                    'title': metadata.get('title', _('Book ID {0}').format(book_id)),
                    'field_data': field_data,
                    'status': 'applied' if approved_data else 'skipped',
                })
            else:
                from calibre_plugins.ai_vision_metadata.ui import MetadataReviewDialog
                d = MetadataReviewDialog(self.gui, metadata, cover_path, enabled_fields,
                                         provenance=metadata.get('_provenance', {}))
                result = d.exec_()
                approved_data = d.get_approved_data() if result == d.Accepted else None
                d.setParent(None)
                d.deleteLater()
                if approved_data:
                    self.apply_metadata(book_id, approved_data)

        except Exception as e:
            if getattr(self, 'batch_auto_apply', False):
                self._batch_log.append({
                    'book_id': str(book_id), 'title': _('Book ID {0}').format(book_id),
                    'field_data': [], 'status': 'error', 'error': str(e),
                })
            else:
                from calibre.gui2 import error_dialog
                error_dialog(self.gui, _('UI Error'), _('Could not process book: {0}').format(str(e)), show=True)

        finally:
            self.process_next_in_queue()

    def _show_error_dialog(self, error_msg):
        """Displays error messages. In batch mode, logs silently instead of blocking."""
        if getattr(self, 'batch_auto_apply', False):
            self._batch_log.append({
                'book_id': '', 'title': _('Unknown'),
                'field_data': [], 'status': 'error', 'error': error_msg,
            })
            self.process_next_in_queue()
        else:
            from calibre.gui2 import error_dialog
            error_dialog(self.gui, _("AI Vision Error"), error_msg, show=True)

    def _show_batch_summary(self):
        from calibre_plugins.ai_vision_metadata.ui import BatchSummaryDialog
        d = BatchSummaryDialog(self.gui, self._batch_log)
        d.exec_()
        d.setParent(None)
        d.deleteLater()

    def apply_metadata(self, book_id, approved_data):
        db = self.gui.current_db.new_api
        mi = db.get_metadata(book_id)
        
        # 1. Set Languages First (Crucial for the title_sort algorithm)
        if 'languages' in approved_data:
            # Calibre expects lowercase 3-letter codes
            langs = [l.strip().lower() for l in approved_data['languages'].split(',') if l.strip()]
            if langs:
                mi.languages = langs

        # 2. Set Title and Title Sort (Passing the language we just extracted)
        if 'title' in approved_data: 
            mi.title = approved_data['title']
            from calibre.ebooks.metadata import title_sort
            # Safely grab the primary language code to feed the sort routine
            lang_code = mi.languages[0] if mi.languages else None
            mi.title_sort = title_sort(mi.title, lang=lang_code)
            
        if 'authors' in approved_data:
            authors = [a.strip() for a in approved_data['authors'].split(',') if a.strip()]
            if authors: 
                mi.authors = authors
                
                # Import the standalone function from Calibre's metadata tools
                from calibre.ebooks.metadata import authors_to_sort_string
                mi.author_sort = authors_to_sort_string(mi.authors)
                
        if 'publisher' in approved_data:
            mi.publisher = approved_data['publisher']
            
        if 'pubdate' in approved_data:
            try:
                import datetime
                mi.pubdate = datetime.datetime.strptime(approved_data['pubdate'], "%Y-%m-%d")
            except ValueError:
                pass

        # --- 2. Identifiers (Merge Dictionaries) ---
        if 'identifiers' in approved_data:
            new_ids_str = approved_data['identifiers']
            
            # Calibre stores identifiers as a dictionary (e.g., {'isbn': '1234', 'issn': '5678'})
            existing_ids = mi.identifiers if mi.identifiers else {}
            
            # Parse the AI's comma-separated string and inject it into the dictionary
            for pair in new_ids_str.split(','):
                if ':' in pair:
                    key, val = pair.split(':', 1)
                    # This updates existing keys or adds new ones without destroying the rest
                    existing_ids[key.strip().lower()] = val.strip()
            
            mi.identifiers = existing_ids

        # --- 3. Pass the metadata to Calibre's new_api cache ---
        db.set_metadata(book_id, mi)
        
        # --- 5. Force the UI to redraw ---
        self.gui.library_view.model().refresh_ids([book_id])