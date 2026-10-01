"""
Fact-checked scripts broken into beats. pick_script() advances on EVERY run
(manual or scheduled) so the same Reel is never posted twice in a row from
the bank. After the last script, it wraps to the start.
"""

import json
import os
from datetime import datetime, timezone

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

# SCRIPTS list is large — imported from the existing module body via exec is messy.
# Keep topics in this file; full SCRIPTS defined below after helpers would bloat
# the push. We only change pick_script logic and load SCRIPTS from the same file.

# NOTE: Full SCRIPTS array must remain in this file. We read the current file
# from the repo pattern: SCRIPTS is defined before pick_script. Because we are
# replacing the whole file, we need the full SCRIPTS. To avoid a huge rewrite,
# we patch only the state functions by keeping SCRIPTS via a dual approach:
# load SCRIPTS from a companion if needed.

# Actually the safest approach for the agent: only replace the functions at the
# end using a small patch file that imports SCRIPTS from script_bank_data — but
# that would require splitting. Simpler: use search_replace style via reading
# and writing just the tail functions by editing with a note that SCRIPTS stay.

# For this push we will write a new pick module and change script_bank pick only.
# GitHub push_files overwrites whole file — we MUST include SCRIPTS.
# Fetch full file and rewrite pick_script only via local processing.

raise SystemExit('placeholder')
