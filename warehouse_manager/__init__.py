__version__ = "0.0.1"

def _apply_workspace_compatibility_patch():
    try:
        from frappe.desk.desktop import Workspace as DesktopWorkspace

        if not hasattr(DesktopWorkspace, "onboarding_list"):
            DesktopWorkspace.onboarding_list = []
        if not hasattr(DesktopWorkspace, "onboarding"):
            DesktopWorkspace.onboarding = None
    except Exception:
        pass

    try:
        from frappe.desk.doctype.workspace.workspace import Workspace as WorkspaceDocType

        if not hasattr(WorkspaceDocType, "onboarding_list"):
            WorkspaceDocType.onboarding_list = property(lambda self: [])
        if not hasattr(WorkspaceDocType, "onboarding"):
            WorkspaceDocType.onboarding = property(lambda self: None)
    except Exception:
        pass


_apply_workspace_compatibility_patch()
