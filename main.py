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
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _hook


def main():
    logger = _setup_logging()
    _install_excepthook(logger)

    from constants import APP_NAME, APP_VERSION
    logger.info(f"{APP_NAME} v{APP_VERSION} starting")

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
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
