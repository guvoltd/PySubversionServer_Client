"""Entry point for the SVN Client application.

Usage:
    python -m svn_client
    svn-client  (if installed via pip/pipx)
"""

import os
import sys


def main() -> int:
    """Launch the SVN Client GUI."""
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from svn_client.app import ClientMainWindow

    app = QApplication(sys.argv)
    app.setOrganizationName("svnsuite")
    app.setApplicationName("svn-client")
    app.setApplicationVersion("0.1.0")

    icon_path = os.path.join(
        os.path.dirname(__file__), "resources", "icons", "org.svnsuite.SvnClient.ico"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    from svn_shared.crash_handler import install_crash_handler
    install_crash_handler("svn-client")

    window = ClientMainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
