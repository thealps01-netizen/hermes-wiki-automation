"""Hermes' own plugin doctor passes this checkout with no finding.

`hermes plugins doctor` loads the plugin through the real scanner and registration path and warns
about every tool or hook the manifest does not list; the plugin list and activation summary read the
same manifest fields to say what a plugin adds. Until 2.3.8 plugin.yaml listed none of the three
tools and six hooks, so doctor printed nine warnings on every check. This test runs that doctor
rather than re-implementing its comparison.
"""
from pathlib import Path
import unittest


class PluginDoctorTests(unittest.TestCase):
    def test_doctor_reports_no_error_or_warning(self):
        from hermes_cli.plugin_dev import doctor_plugin
        report = doctor_plugin(Path(__file__).resolve().parents[1])
        self.assertTrue(report.registered_tools, report.format_text())
        self.assertTrue(report.registered_hooks, report.format_text())
        self.assertEqual([f'{f.level}: {f.message}' for f in report.findings], [], report.format_text())


if __name__ == '__main__':
    unittest.main()
