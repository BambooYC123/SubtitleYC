"""Test package.

Importing it points SubtitleYC at a throwaway workspace, so test runs never write to
the real one's logs, settings or library. Run the suite from the repository root with
``python -m unittest discover -s tests -t .`` so this file is loaded first.
"""

import os
import tempfile

os.environ.setdefault("SUBTITLEYC_DATA_DIR", tempfile.mkdtemp(prefix="subtitleyc-tests-"))
