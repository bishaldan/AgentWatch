from django import forms

from .models import ResourceType, SessionClassification


class SessionFilterForm(forms.Form):
    classification = forms.ChoiceField(
        choices=[("", "All classifications"), *SessionClassification.choices],
        required=False,
    )
    resource_type = forms.ChoiceField(
        choices=[("", "All resource types"), *ResourceType.choices],
        required=False,
    )
    referrer = forms.CharField(required=False)
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
