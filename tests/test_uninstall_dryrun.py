import sys
import os
import pytest

# ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from assistant.actions import execute_action


def _call_uninstall(params):
    action = {'type': 'uninstall', 'parameters': params}
    return execute_action(action)


@pytest.mark.skipif(os.name != 'nt', reason='Windows-only UI automation tests')
def test_uninstall_dry_run_returns_diagnostic():
    res = _call_uninstall({'name': 'WPS', 'dry_run': True})
    # dry_run should not attempt destructive actions; expect diagnostic or a clear message
    assert isinstance(res, dict)
    # either diagnostic present or ok False with say explaining lack of UI automation
    assert 'diagnostic' in res or 'say' in res


@pytest.mark.skipif(os.name != 'nt', reason='Windows-only UI automation tests')
def test_uninstall_require_confirm_reports_ready():
    res = _call_uninstall({'name': 'WPS', 'dry_run': False, 'require_confirm': True})
    assert isinstance(res, dict)
    # Should not perform destructive clicks; either ready message or failure explaining missing automation
    assert 'say' in res
