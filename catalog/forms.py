import uuid
from django import forms
from .models import ProductVariant


class ProductVariantForm(forms.ModelForm):
    """
    Custom form for admin inline.

    Why: Django's formset validates uniqueness of SKU across all inline rows
    BEFORE save() runs. Multiple empty SKUs ('') are treated as duplicates.
    Solution: substitute each empty SKU with a unique placeholder that passes
    validation, then auto-generate the real SKU in ProductVariant.save().
    """

    class Meta:
        model = ProductVariant
        exclude = ("stock",)

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()
        if not sku:
            # Unique placeholder - passed to formset validation.
            # Will be replaced with a real SKU in save().
            return f"__TMP__{uuid.uuid4().hex[:12].upper()}"
        return sku
