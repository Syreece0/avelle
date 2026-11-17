"""Shared form styling: puts the AVELLE classes on every widget (see components/form_field.html)."""
from django import forms


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxInput,)):
                continue  # checkboxes use the .check component in templates
            if isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{css} select".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"{css} textarea".strip()
            else:
                widget.attrs["class"] = f"{css} input".strip()
