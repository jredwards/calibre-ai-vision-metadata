# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from qt.core import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit, QComboBox, QCheckBox, QDialogButtonBox, QTextEdit, QPixmap, Qt, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QColor, QFont, QBrush

try:
    load_translations()
except NameError:
    pass

class MetadataReviewDialog(QDialog):
    def __init__(self, parent, metadata, cover_path, enabled_fields=None, provenance=None):
        super().__init__(parent)
        self.setWindowTitle(_("Review AI Metadata"))
        self.setMinimumWidth(900)

        self.layout = QVBoxLayout(self)
        self.metadata = metadata
        self.results = {}

        if enabled_fields is None:
            enabled_fields = ['title', 'authors', 'languages', 'publisher', 'pubdate', 'identifiers']
        if provenance is None:
            provenance = {}

        _GB_STATUS_LABEL = {
            'verified':     _('AI scan \u00b7 verified'),
            'corrected':    _('AI scan \u00b7 verified'),
            'title_only':   _('AI scan \u00b7 author unverified'),
            'unverified':   _('AI scan \u00b7 no Google Books match'),
            'rate_limited': _('AI scan \u00b7 rate limited'),
        }
        
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

            # Build sub-label: mode + provenance source when available
            p = provenance.get(key, {})
            if p.get('ai') and p.get('gb'):
                source = _('AI scan \u00b7 corrected by Google Books')
            elif p.get('ai') is None and p.get('gb'):
                source = _('from Google Books')
            else:
                source = _GB_STATUS_LABEL.get(p.get('gb_status', ''), '')
            mode_text = f"{mode} \u00b7 {source}" if source else mode
            rich_label = f"{label_text}<br><span style='color: gray; font-size: 10px;'><i>({mode_text})</i></span>"
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
    """Post-batch summary — flat table showing every field change at a glance."""

    def __init__(self, parent, batch_log):
        super().__init__(parent)
        self.setWindowTitle(_("Batch Processing Summary"))
        self.setMinimumWidth(800)
        self.setMinimumHeight(450)

        layout = QVBoxLayout(self)

        applied = sum(1 for e in batch_log if e['status'] == 'applied')
        skipped = sum(1 for e in batch_log if e['status'] == 'skipped')
        errors  = sum(1 for e in batch_log if e['status'] == 'error')

        summary = QLabel(_(
            "<b>Processed {total} books:</b> {applied} applied, {skipped} skipped, {errors} errors."
        ).format(total=len(batch_log), applied=applied, skipped=skipped, errors=errors))
        summary.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(summary)

        # Per-state display config: (symbol_prefix, hex_color, bold)
        _GB_STYLE = {
            'verified':     ('\u2713 ', '#2e7d32', False),   # green
            'corrected':    ('\u2192 ', '#1565c0', True),    # bold blue, arrow
            'enriched':     ('+ ',      '#1565c0', False),   # blue
            'unverified':   ('\u26a0 ', '#e65100', False),   # orange
            'rate_limited': ('\u29d7 ', '#757575', False),   # gray
            'error':        ('\u2717 ', '#c62828', False),   # red
            'skipped':      ('\u2013 ', '#757575', False),   # gray
        }

        # Build flat row list: (book_id, field, original_value, ai_value, gb_value, gb_state)
        rows = []
        for entry in batch_log:
            book_id    = entry.get('book_id', '')
            book_title = entry['title']
            if entry['status'] == 'error':
                rows.append((book_id, _('Error'), book_title, '', entry.get('error', ''), 'error'))
            elif entry['status'] == 'skipped':
                rows.append((book_id, '\u2013', book_title, '', _('No metadata extracted'), 'skipped'))
            else:
                for fd in entry.get('field_data', []):
                    rows.append((book_id, fd['field'],
                                 fd.get('original_value', ''),
                                 fd['ai_value'], fd['gb_value'],
                                 fd.get('gb_state', '')))

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels([_("ID"), _("Field"), _("Original Value"),
                                         _("AI Scan"), _("Google Books Verification")])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)

        for row_idx, (book_id, field, orig_val, ai_val, gb_val, gb_state) in enumerate(rows):
            table.setItem(row_idx, 0, QTableWidgetItem(book_id))
            table.setItem(row_idx, 1, QTableWidgetItem(field))
            table.setItem(row_idx, 2, QTableWidgetItem(orig_val))
            table.setItem(row_idx, 3, QTableWidgetItem(ai_val))

            symbol, color_hex, bold = _GB_STYLE.get(gb_state, ('', None, False))
            gb_item = QTableWidgetItem(symbol + gb_val)
            if color_hex:
                gb_item.setForeground(QBrush(QColor(color_hex)))
            if bold:
                f = QFont()
                f.setBold(True)
                gb_item.setFont(f)
            table.setItem(row_idx, 4, gb_item)

        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)