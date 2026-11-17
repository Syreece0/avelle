from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.catalog.models import Brand, Category, Colour, Size

from ..access import dashboard_required
from ..forms import BrandForm, CategoryForm, ColourForm, SizeForm
from .common import page


@dashboard_required("catalogue")
def categories(request):
    roots = Category.objects.filter(parent__isnull=True).annotate(n=Count("products", distinct=True)).prefetch_related("children")
    counts = dict(Category.objects.annotate(n=Count("products")).values_list("pk", "n"))
    tree = [{"cat": r, "children": [{"cat": c, "n": counts.get(c.pk, 0)} for c in r.children.all()], "n": counts.get(r.pk, 0)} for r in roots]
    return page(request, "dashboard/categories.html", "categories", tree=tree)


@dashboard_required("catalogue")
def category_edit(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"{saved.name} saved.")
        return redirect("dashboard:categories")
    return page(request, "dashboard/simple_form.html", "categories", form=form, title="Edit category" if category else "New category",
                back=("dashboard:categories", "Categories"), multipart=True, delete_url=f"/dashboard/categories/{pk}/delete/" if pk else "",
                delete_message=f"Delete {category.name}? This only works if it has no products or subcategories." if category else "")


@dashboard_required("catalogue")
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    try:
        category.delete()
        messages.success(request, f"{category.name} deleted.")
    except ProtectedError:
        messages.error(request, f"{category.name} still has products or subcategories. Move or delete them first, or hide the category instead.")
    return redirect("dashboard:categories")


# ---- brands, sizes, colours share one pattern
KINDS = {
    "brand": (Brand, BrandForm, "Brand"),
    "size": (Size, SizeForm, "Size"),
    "colour": (Colour, ColourForm, "Colour"),
}


@dashboard_required("catalogue")
def attributes(request):
    return page(request, "dashboard/attributes.html", "attributes", brands=Brand.objects.annotate(n=Count("products")),
                sizes=Size.objects.annotate(n=Count("variants")), colours=Colour.objects.annotate(n=Count("variants")))


@dashboard_required("catalogue")
def attribute_edit(request, kind, pk=None):
    if kind not in KINDS:
        return redirect("dashboard:attributes")
    model, form_class, label = KINDS[kind]
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{label} saved.")
        return redirect("dashboard:attributes")
    return page(request, "dashboard/simple_form.html", "attributes", form=form, title=f"{'Edit' if obj else 'New'} {label.lower()}",
                back=("dashboard:attributes", "Attributes"), delete_url=f"/dashboard/attributes/{kind}/{pk}/delete/" if pk else "",
                delete_message=f"Delete {obj}? It can't be deleted while products use it." if obj else "")


@dashboard_required("catalogue")
@require_POST
def attribute_delete(request, kind, pk):
    if kind in KINDS:
        model, _, label = KINDS[kind]
        obj = get_object_or_404(model, pk=pk)
        try:
            obj.delete()
            messages.success(request, f"{label} deleted.")
        except ProtectedError:
            messages.error(request, f"{obj} is used by products, so it can't be deleted.")
    return redirect("dashboard:attributes")
