# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from qt.core import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QLineEdit, QComboBox, QCheckBox, QPushButton, QDialogButtonBox, QTextEdit, QPixmap, Qt, QTreeWidget, QTreeWidgetItem, QHeaderView

try:
    load_translations()
except NameError:
    pass

class MetadataReviewDialog(QDialog):
    def __init__(self, parent, metadata, cover_path, enabled_fields=None):
        super().__init__(parent)
        self.setWindowTitle(_("Review AI Metadata"))
        self.setMinimumWidth(900)

        self.layout = QVBoxLayout(self)
        self.metadata = metadata
        self.results = {}

        # Fall back to all fields if no preference has been saved yet
        ALL_FIELD_KEYS = ['title', 'authors', 'series', 'series_index', 'tags',
                          'languages', 'publisher', 'pubdate', 'identifiers', 'comments']
        if enabled_fields is None:
            enabled_fields = ALL_FIELD_KEYS
        
        # --- Centered Model Header ---
        model_name = metadata.get('ai_model_used', _('Unknown Model'))
        provider_name = metadata.get('ai_provider', _('AI'))
        duration = metadata.get('api_duration', 0.0)
        
        # Build a dynamic string with the provider, model, and formatted elapsed time
        header_text = _("<center><b>{0} : {1}</b><br><span style='color: gray; font-size: 10px;'><i>(Processed in {2} seconds)</i></span></center>").format(provider_name, model_name, duration)
        
        self.header_label = QLabel(header_text)
        self.layout.addWidget(self.header_label)
        
        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(self.line)
        # ----------------------------------

        # --- Google Books Verification Banner ---
        verification = metadata.get('_verification')
        if verification:
            status      = verification.get('status', 'unverified')
            corrections = verification.get('corrections', {})
            title_fix   = corrections.get('title')
            author_fix  = corrections.get('authors')

            # Build individual correction lines
            lines = []
            if title_fix:
                lines.append(_('\u270e Title: \u201c{0}\u201d \u2192 \u201c{1}\u201d').format(
                    title_fix.get('from', ''), title_fix.get('to', '')))
            if author_fix:
                from_val = author_fix.get('from')
                to_val   = author_fix.get('to', '')
                if from_val:
                    lines.append(_('\u270e Author: \u201c{0}\u201d \u2192 \u201c{1}\u201d').format(from_val, to_val))
                else:
                    lines.append(_('\u270e Author supplied: \u201c{0}\u201d').format(to_val))

            if status == 'verified':
                badge_color = '#2e7d32'   # green
                badge_text  = _('\u2713 Verified against Google Books')
            elif status == 'corrected':
                badge_color = '#1565c0'   # blue
                badge_text  = _('\u270e Corrected via Google Books') + (
                    '<br>' + '<br>'.join(lines) if lines else '')
            elif status == 'title_only':
                badge_color = '#e65100'   # amber
                badge_text  = _('\u26a0 Title matched on Google Books but author could not be verified')
                if lines:
                    badge_text += '<br>' + '<br>'.join(lines)
            elif status == 'rate_limited':
                badge_color = '#c62828'   # red
                badge_text  = _('\u29d7 Google Books rate limit reached — verification skipped')
            else:
                badge_color = '#757575'   # grey
                badge_text  = _('\u2013 Could not verify against Google Books')

            banner = QLabel(f"<span style='color:{badge_color}; font-size:11px;'>{badge_text}</span>")
            banner.setWordWrap(True)
            banner.setContentsMargins(4, 4, 4, 4)
            self.layout.addWidget(banner)
        # ----------------------------------

        # --- Side-by-Side Layout Container ---
        self.middle_layout = QHBoxLayout()
        
        # 1. Left Side: The Cover Image
        self.cover_label = QLabel()
        if cover_path:
            import os
            if os.path.exists(cover_path):
                pixmap = QPixmap(cover_path)
                if not pixmap.isNull():
                    # Scale the image height to match the form, keeping it looking sharp
                    scaled_pixmap = pixmap.scaledToHeight(450, Qt.TransformationMode.SmoothTransformation)
                    self.cover_label.setPixmap(scaled_pixmap)
        
        # Pin the image to the top left so it doesn't float weirdly
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.middle_layout.addWidget(self.cover_label)
        
        # 2. Right Side: The Form
        self.form_layout = QVBoxLayout()
        self.row_counter = 0
        
        # --- HELPER FUNCTIONS (Zebra Striped Rows) ---
        def create_row_container():
            row_frame = QFrame()
            row_frame.setObjectName("formRow")
            if self.row_counter % 2 != 0:
                row_frame.setStyleSheet("QFrame#formRow { background-color: rgba(128, 128, 128, 64); border-radius: 4px; }")
            self.row_counter += 1
            
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(5, 5, 5, 5)
            return row_frame, row_layout

        def add_field(key, label_text, value, mode):
            row_frame, row_layout = create_row_container()
            
            # Injecting a muted, italicized sub-label
            rich_label = f"{label_text}<br><span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            label.setFixedWidth(130)
            row_layout.addWidget(label)
            
            edit = QLineEdit(str(value) if value else "")
            row_layout.addWidget(edit, 1) 
            
            chk = QCheckBox()
            has_data = bool(str(value).strip() if value else False)
            chk.setChecked(has_data)
            row_layout.addWidget(chk)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': edit}

        def add_indented_combo_field(key, label_text, options, mode):
            row_frame, row_layout = create_row_container()
            
            unique_opts = []
            for opt in options:
                if opt and opt not in unique_opts:
                    unique_opts.append(opt)

            spacer = QLabel()
            spacer.setFixedWidth(130)
            row_layout.addWidget(spacer)
            
            row_layout.addStretch(1)
            
            # For the indented fields, we keep the mode text inline rather than breaking to a new line
            rich_label = f"{label_text} <span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            row_layout.addWidget(label)
            
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(unique_opts)
            combo.setMinimumWidth(120) 
            row_layout.addWidget(combo)
            
            chk = QCheckBox()
            chk.setChecked(bool(unique_opts))
            row_layout.addWidget(chk)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': combo}

        def add_text_area(key, label_text, value, mode):
            row_frame, row_layout = create_row_container()
            
            rich_label = f"{label_text}<br><span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            label.setFixedWidth(130)
            row_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignTop)
            
            edit = QTextEdit()
            edit.setPlainText(str(value) if value else "")
            edit.setMaximumHeight(80) 
            row_layout.addWidget(edit, 1)
            
            chk = QCheckBox(self)
            has_data = bool(str(value).strip() if value else False)
            chk.setChecked(has_data)
            row_layout.addWidget(chk, alignment=Qt.AlignmentFlag.AlignTop)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': edit}

        # --- BUILD THE FORM ---
        if 'title' in enabled_fields:
            add_field("title", _("Title"), metadata.get('title', ''), _("Replaces"))

        if 'authors' in enabled_fields:
            raw_creators = metadata.get('creators')
            if not raw_creators:
                rogue_editor = metadata.get('editor')
                rogue_author = metadata.get('author')
                if rogue_editor: raw_creators = [rogue_editor]
                elif rogue_author: raw_creators = [rogue_author]
                else: raw_creators = []
            creators_str = ", ".join(raw_creators) if isinstance(raw_creators, list) else str(raw_creators)
            add_field("authors", _("Authors"), creators_str, _("Replaces"))

        if 'series' in enabled_fields or 'series_index' in enabled_fields:
            series_val = str(metadata.get('series', '')).strip()
            vol = str(metadata.get('volume', '')).strip()
            iss = str(metadata.get('issue_number', '')).strip()
            direct_index = str(metadata.get('series_index', '')).strip()

            index_options = []
            if direct_index and direct_index not in ('None', 'null', ''):
                index_options.append(direct_index)
            if vol and iss and vol.isdigit() and iss.isdigit():
                combined = f"{vol}.{iss.zfill(2)}"
                if combined not in index_options:
                    index_options.append(combined)
            if iss and iss not in index_options:
                index_options.append(iss)
            if vol and vol not in index_options:
                index_options.append(vol)
            if 'series' in enabled_fields:
                add_indented_combo_field('series', _('Series:'), [series_val], _("Replaces"))
            if 'series_index' in enabled_fields:
                add_indented_combo_field('series_index', _('Series Index:'), index_options, _("Replaces"))

        if 'tags' in enabled_fields:
            tags_str = ", ".join(metadata.get('tags', [])) if isinstance(metadata.get('tags', []), list) else str(metadata.get('tags', ''))
            add_field("tags", _("Tags"), tags_str, _("Merges"))

        if 'languages' in enabled_fields:
            langs_str = ", ".join(metadata.get('languages', ['eng'])) if isinstance(metadata.get('languages', ['eng']), list) else str(metadata.get('languages', 'eng'))
            add_field("languages", _("Languages"), langs_str, _("Replaces"))

        if 'publisher' in enabled_fields:
            add_field("publisher", _("Publisher"), metadata.get('publisher', ''), _("Replaces"))

        if 'pubdate' in enabled_fields:
            year_raw = metadata.get('pub_year')
            if year_raw and str(year_raw).strip().isdigit():
                year = str(year_raw).strip()
                month_raw = metadata.get('pub_month')
                month = str(month_raw).strip().zfill(2) if month_raw and str(month_raw).strip().isdigit() else "01"
                day_raw = metadata.get('pub_day')
                day = str(day_raw).strip().zfill(2) if day_raw and str(day_raw).strip().isdigit() else "01"
                pub_date = f"{year}-{month}-{day}"
            else:
                pub_date = ""
            add_field("pubdate", _("Published"), pub_date, _("Replaces"))

        if 'identifiers' in enabled_fields:
            add_field("identifiers", _("Identifiers"), metadata.get('identifiers', ''), _("Merges"))

        if 'comments' in enabled_fields:
            add_text_area("comments", _("Comments"), metadata.get('comments', ''), _("Appends"))

        self.form_layout.addStretch(1)

        # Add the completed form to the right side of the middle layout
        self.middle_layout.addLayout(self.form_layout)
        
        # Add the entire middle layout to the main window
        self.layout.addLayout(self.middle_layout)

        # --- AI Disclaimer & Buttons (Spans the full width at the bottom) ---
        disclaimer_text = _(
            "<i><b>Note:</b> The metadata above was generated by an AI model and may contain errors or inaccuracies. "
            "Please review each field carefully. Use the checkboxes to strictly control whether "
            "this new data should overwrite or be appended to your existing Calibre library data.</i>"
        )
        self.disclaimer_label = QLabel(disclaimer_text)
        self.disclaimer_label.setWordWrap(True)
        font = self.disclaimer_label.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        self.disclaimer_label.setFont(font)
        self.disclaimer_label.setContentsMargins(0, 10, 0, 10) 
        self.layout.addWidget(self.disclaimer_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def get_approved_data(self):
        approved = {}
        for key, data in self.results.items():
            chk = data['checkbox']
            widget = data['widget']
            
            if chk.isChecked():
                if isinstance(widget, QComboBox):
                    approved[key] = widget.currentText().strip()
                elif isinstance(widget, QTextEdit):
                    approved[key] = widget.toPlainText().strip()
                else:
                    approved[key] = widget.text().strip()
        return approved


class BatchSummaryDialog(QDialog):
    """Post-batch summary showing what was applied, skipped, or errored per book."""

    _STATUS_LABELS = {
        'applied':  'Applied',
        'skipped':  'Skipped (no data)',
        'error':    'Error',
    }
    _VERIFICATION_LABELS = {
        'verified':     '✓ Verified',
        'corrected':    '✎ Corrected',
        'title_only':   '⚠ Title only',
        'unverified':   '– Unverified',
        'rate_limited': '⊗ Rate limited',
        '':             '',
    }

    def __init__(self, parent, batch_log):
        super().__init__(parent)
        self.setWindowTitle(_("Batch Processing Summary"))
        self.setMinimumWidth(700)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        applied = sum(1 for e in batch_log if e['status'] == 'applied')
        skipped = sum(1 for e in batch_log if e['status'] == 'skipped')
        errors  = sum(1 for e in batch_log if e['status'] == 'error')

        summary = QLabel(_(
            "<b>Processed {total} books:</b> {applied} applied, {skipped} skipped, {errors} errors."
        ).format(total=len(batch_log), applied=applied, skipped=skipped, errors=errors))
        summary.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(summary)

        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([_("Book"), _("Status"), _("Google Books")])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.setRootIsDecorated(True)

        for entry in batch_log:
            status_label = self._STATUS_LABELS.get(entry['status'], entry['status'])
            verification_label = self._VERIFICATION_LABELS.get(entry.get('verification', ''), '')
            row = QTreeWidgetItem([entry['title'], status_label, verification_label])

            if entry['status'] == 'error':
                child = QTreeWidgetItem([entry.get('error', ''), '', ''])
                row.addChild(child)
            elif entry.get('fields'):
                child = QTreeWidgetItem([', '.join(entry['fields']), '', ''])
                row.addChild(child)

            tree.addTopLevelItem(row)

        layout.addWidget(tree)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)