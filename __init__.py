"""Hermes entry point of Wiki Automation. The panel is dashboard/ and desktop/, the engine is engine/.
Since 2.13.3 the plugin registers no tool and no hook: the drafting toolset and its veto were removed
with the drafting agent job (Docs/owner-approval.md)."""


def register(ctx):
    return None
