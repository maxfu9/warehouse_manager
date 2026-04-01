__version__ = "0.0.1"

# Apply v15 workspace compatibility as early as possible.
try:
    from frappe.desk.doctype.workspace.workspace import Workspace

    if not hasattr(Workspace, "onboarding_list"):
        Workspace.onboarding_list = property(lambda self: [])
    if not hasattr(Workspace, "onboarding"):
        Workspace.onboarding = property(lambda self: None)
except Exception:
    pass
