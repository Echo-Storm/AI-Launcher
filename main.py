# main.py — AI Writing Tools Launcher

import logging
import os
import sys


def _setup_logging() -> logging.Logger:
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, "AI_Launcher_Log.txt")

    fmt    = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    try:
        fh = logging.FileHandler(log_path, mode='w', encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def _install_excepthook(logger: logging.Logger):
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _hook


def _check_config() -> bool:
    """Return True if config.json is present. Show a dialog and return False if not."""
    here        = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(here, "config.json")
    example_path = os.path.join(here, "config.example.json")

    if os.path.isfile(config_path):
        return True

    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)

    msg = QMessageBox()
    msg.setWindowTitle("AI Writing Tools — Setup Required")
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setText("config.json not found.")
    msg.setInformativeText(
        "Copy config.example.json to config.json and fill in your paths, "
        "then launch the app again.\n\n"
        f"Example:  {example_path}\n"
        f"Create:   {config_path}"
    )
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()
    return False


_SINGLE_INSTANCE_MUTEX = "AIWritingToolsLauncher_SingleInstance_Mutex_2b6f7e"
_APP_WINDOW_TITLE = "AI Writing Tools"  # matches constants.APP_NAME — hardcoded so
                                        # this check never depends on config.json
                                        # existing (constants.py is fatal without it)


def main():
    logger = _setup_logging()
    _install_excepthook(logger)

    import singleinstance
    if not singleinstance.acquire(_SINGLE_INSTANCE_MUTEX):
        logger.warning("Another instance is already running — focusing it and exiting.")
        singleinstance.focus_existing_window(_APP_WINDOW_TITLE)
        singleinstance.notify_already_running(_APP_WINDOW_TITLE)
        sys.exit(0)

    if not _check_config():
        sys.exit(0)

    try:
        from constants import APP_NAME, APP_VERSION
    except SystemExit as e:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Configuration Error", str(e))
        logger.error(f"Config error: {e}")
        sys.exit(1)

    logger.info(f"{APP_NAME} v{APP_VERSION} starting")

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    from ui import MainWindow
    window = MainWindow()
    window.show()

    logger.info("MainWindow shown — entering event loop")
    exit_code = app.exec()
    logger.info(f"Exiting with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
