"""Commands the engine prints point at the engine folder, never at the data folder.

The data folder holds state only; engine scripts run from the installed release. A hint built as
`AUDIT_DIR / 'x.py'` names a file that does not exist there, so the owner copies a dead command.
"""
import re
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
DATA_SCRIPT = re.compile(r"AUDIT_DIR\s*/\s*['\"][\w-]+\.py|\{AUDIT_DIR\}[\\/][\w-]+\.py|llmwiki-audit[\\/]+[\w-]+\.py")


class HintPathTests(unittest.TestCase):
    def test_no_printed_command_names_a_script_in_the_data_folder(self):
        found = [f'{path.name}:{number}' for path in sorted(ENGINE.glob('*.py'))
                 for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
                 if DATA_SCRIPT.search(line)]
        self.assertEqual(found, [])

    def test_the_pattern_catches_each_old_form(self):
        for line in ("f\"python {AUDIT_DIR / 'wiki_audit.py'}\"", 'f"python {AUDIT_DIR}/wiki_audit.py"',
                     '"Committed by ~/.llmwiki-audit/wiki_autocommit.py"'):
            self.assertRegex(line, DATA_SCRIPT)


if __name__ == '__main__':
    unittest.main()
