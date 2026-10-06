"""Blender UI package; pure workflow helpers can also be imported outside Blender."""
def register():
    from .semantic_graybox_panel import register as register_panel
    register_panel()
def unregister():
    from .semantic_graybox_panel import unregister as unregister_panel
    unregister_panel()
__all__ = ["register", "unregister"]