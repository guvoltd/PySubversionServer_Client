"""PyInstaller entry point -- thin wrapper around svn_client.__main__.main()."""

import sys

from svn_client.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
