# imagegen_dialog.py — In-process SDXL image generator (txt2img + LoRA + TI + ESRGAN hires-fix)

import os
import shutil

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout,
)

import imagegen_engine
from constants import (
    COLOR_ACCENT, COLOR_ACCENT_DIM, COLOR_BG, COLOR_BORDER, COLOR_BORDER_BRIGHT,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER, COLOR_PANEL, COLOR_STATUS_ERROR,
    COLOR_STATUS_RUNNING, COLOR_TEXT, COLOR_TEXT_MUTED,
    FONT_UI_FAMILY, FONT_UI_SIZE,
)

_STYLE = f"""
QDialog {{
    background: {COLOR_BG};
}}
QWidget {{
    background: {COLOR_BG};
    font-family: {FONT_UI_FAMILY};
    font-size: {FONT_UI_SIZE}pt;
    color: {COLOR_TEXT};
}}
QLabel {{
    color: {COLOR_TEXT};
    background: transparent;
}}
QPlainTextEdit {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 6px;
}}
QPlainTextEdit:focus {{
    border-color: {COLOR_ACCENT_DIM};
}}
QPushButton {{
    background: {COLOR_BUTTON_BG};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 12px;
}}
QPushButton:hover:enabled {{
    background: {COLOR_BUTTON_HOVER};
    border-color: {COLOR_ACCENT_DIM};
}}
QPushButton:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}
QPushButton#accent {{
    background: {COLOR_ACCENT_DIM};
    border-color: {COLOR_ACCENT};
}}
QPushButton#accent:hover:enabled {{
    background: {COLOR_ACCENT};
}}
QProgressBar {{
    background: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    text-align: center;
    color: {COLOR_TEXT};
}}
QProgressBar::chunk {{
    background: {COLOR_ACCENT_DIM};
    border-radius: 3px;
}}
"""

class _Cancelled(Exception):
    pass


class ImageGenWorker(QThread):
    progress      = pyqtSignal(str)
    step_progress = pyqtSignal(int, int)  # (current_step, total_steps) within the current pass
    finished      = pyqtSignal(str)  # output file path
    error         = pyqtSignal(str)
    cancelled     = pyqtSignal()

    def __init__(self, prompt: str, negative_prompt: str = "", parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self._cancel_requested = False

    def request_cancel(self):
        # Cooperative — checked between diffusion steps, never force-kills
        # the thread. A hard terminate() mid-CUDA-op can corrupt the CUDA
        # context for the whole process, and would also leave the pipeline
        # lock held forever since a killed thread never runs its `finally`.
        self._cancel_requested = True

    def _check_cancel(self, pipe, step_index, timestep, callback_kwargs):
        # pipe.num_timesteps is set internally by diffusers before the
        # denoising loop starts (the actual step count for THIS pass, e.g.
        # the hires-fix img2img pass runs fewer steps than the base pass
        # once `strength` truncates the schedule) -- exactly the total this
        # per-step callback needs, with no extra bookkeeping required.
        total = getattr(pipe, "num_timesteps", 0)
        if total:
            self.step_progress.emit(step_index + 1, total)
        if self._cancel_requested:
            raise _Cancelled()
        return callback_kwargs

    def _raise_if_cancelled(self):
        # Same flag, called directly (not via diffusers' callback signature)
        # for the phases generate_image() runs OUTSIDE a diffusers step loop
        # — currently just the ESRGAN upscale between the base image and the
        # hires-fix pass, which has no per-step hook of its own to check
        # during. Doesn't make the upscale itself interruptible mid-flight,
        # but stops a pending cancel from being silently ignored until the
        # entire (uninterruptible) hires-fix pass also finishes.
        if self._cancel_requested:
            raise _Cancelled()

    def run(self):
        try:
            out_path = imagegen_engine.with_pipeline(self._generate)
            self.finished.emit(out_path)
        except _Cancelled:
            self.cancelled.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _generate(self, pipe, img2img, upscaler, device):
        if self._cancel_requested:
            raise _Cancelled()
        return imagegen_engine.generate_image(
            pipe, img2img, upscaler, device, self.prompt,
            extra_negative_prompt=self.negative_prompt,
            progress_cb=self.progress.emit,
            step_callback=self._check_cancel,
            cancel_check=self._raise_if_cancelled,
        )


class ImageGenDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Gen (Local)")
        self.resize(560, 880)
        self.setStyleSheet(_STYLE)

        self._worker = None
        self._last_output_path = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Prompt"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Describe the scene...")
        self.prompt_edit.setFixedHeight(80)
        layout.addWidget(self.prompt_edit)

        layout.addWidget(QLabel("Negative Prompt (optional)"))
        self.negative_prompt_edit = QPlainTextEdit()
        self.negative_prompt_edit.setPlaceholderText("Things to avoid...")
        self.negative_prompt_edit.setFixedHeight(50)
        layout.addWidget(self.negative_prompt_edit)

        btn_row = QHBoxLayout()
        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setObjectName("accent")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        btn_row.addWidget(self.btn_generate)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.preview_lbl = QLabel()
        self.preview_lbl.setMinimumSize(480, 600)
        self.preview_lbl.setStyleSheet(
            f"background: {COLOR_PANEL}; border: 1px solid {COLOR_BORDER};"
        )
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview_lbl, stretch=1)

        self.btn_save = QPushButton("Save Image...")
        self.btn_save.setEnabled(False)
        layout.addWidget(self.btn_save)

        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_save.clicked.connect(self._on_save)

    # -- busy-state invariant, matching CharGenDialog's _set_busy pattern ----

    def _set_busy(self, busy: bool):
        self.btn_generate.setEnabled(not busy)
        self.prompt_edit.setEnabled(not busy)
        self.negative_prompt_edit.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_cancel.setVisible(busy)

    def _set_status(self, text: str, color: str = COLOR_TEXT_MUTED):
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 8pt;")
        self.status_lbl.setText(text)

    # -- generation ------------------------------------------------------

    def _on_generate(self):
        if self._worker is not None:
            return  # already generating (or cancelling) — Generate is disabled anyway

        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            self._set_status("Enter a prompt first.", COLOR_STATUS_ERROR)
            return
        negative_prompt = self.negative_prompt_edit.toPlainText().strip()

        self._set_busy(True)
        self._set_status("Starting...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate until the first step lands

        self._worker = ImageGenWorker(prompt, negative_prompt, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.step_progress.connect(self._on_step_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _on_progress(self, text: str):
        self._set_status(text)
        # A new phase (base pass / upscale / hires-fix) is starting -- go
        # indeterminate until step_progress tells us this phase's real total
        # (the ESRGAN upscale phase has no per-step hook, so it just stays
        # indeterminate the whole time, which is honest: we don't know).
        self.progress_bar.setRange(0, 0)

    def _on_step_progress(self, step: int, total: int):
        if self.progress_bar.maximum() != total:
            self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(step)

    def _on_done(self, path: str):
        self._last_output_path = path
        pixmap = QPixmap(path).scaled(
            self.preview_lbl.width(), self.preview_lbl.height(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_lbl.setPixmap(pixmap)
        self.btn_save.setEnabled(True)
        self._set_status(f"Done — {os.path.basename(path)}", COLOR_STATUS_RUNNING)
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        self._worker = None

    def _on_error(self, message: str):
        self._set_status(f"Error: {message}", COLOR_STATUS_ERROR)
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        self._worker = None

    def _on_cancelled(self):
        self._set_status("Cancelled.")
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        self._worker = None

    def _on_cancel(self):
        # Cooperative cancel only — never terminate() a thread mid-CUDA-op
        # (see ImageGenWorker.request_cancel). The worker keeps running
        # until its next between-steps checkpoint, then emits `cancelled`.
        if self._worker is not None:
            self.btn_cancel.setEnabled(False)
            self._set_status("Cancelling (finishing current step)...")
            self._worker.request_cancel()

    def _on_save(self):
        if not self._last_output_path:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Image", os.path.basename(self._last_output_path), "PNG Files (*.png)"
        )
        if dest:
            shutil.copy(self._last_output_path, dest)

    def closeEvent(self, event):
        # Cooperative cancel only, and don't wait — this dialog is a reused
        # singleton (hidden, not destroyed), so a still-running worker just
        # finishes or cancels quietly in the background and its signals
        # (still connected to this instance) update state whenever it lands.
        if self._worker is not None:
            self._worker.request_cancel()
        super().closeEvent(event)
