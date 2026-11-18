"""Allow ``python -m bmad_gitlab`` to invoke the CLI."""

import sys

from bmad_gitlab.cli import main

sys.exit(main())
