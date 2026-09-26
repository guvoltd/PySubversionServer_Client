"""Entry point for the SVN Server Admin application.

Usage:
    python -m svn_server
    svn-server-admin  (if installed via pip/pipx)
"""

import logging
import os
import sys

def main() -> int:
    """Launch the SVN Server Admin GUI."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QIcon

    from svn_server.app import ServerMainWindow

    app = QApplication(sys.argv)
    app.setOrganizationName("svnsuite")
    app.setApplicationName("svn-server-admin")
    app.setApplicationVersion("0.1.0")

    icon_path = os.path.join(
        os.path.dirname(__file__), "resources", "icons", "org.svnsuite.SvnServerAdmin.ico"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    settings = QSettings()
    debug_level = int(settings.value("General/debug_level", 0))

    from svn_shared.crash_handler import install_crash_handler
    install_crash_handler("svn-server-admin", debug_level=debug_level)

    window = ServerMainWindow()
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
