from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Colour, Inventory, Product, ProductImage, ProductVariant

from .. import services
from ..access import dashboard_required
from ..forms import ImageAltForm, ProductForm, ProductImagesForm, VariantCreateForm, VariantRowForm
from .common import clean_choice, keep_query, page, paginate

VariantFormSet = modelformset_factory(ProductVariant, form=VariantRowForm, extra=0)


@dashboard_required("catalogue")
def products(request):
    q = (request.GET.get("q") or "").strip()[:80]
    status = clean_choice(request.GET.get("status"), {"draft", "published"})
    stock = clean_choice(request.GET.get("stock"), {"in", "low", "out"})
    category_id = request.GET.get("category") or ""
    qs = Product.objects.select_related("category", "brand").prefetch_related("images").annotate(
        stock=Sum("variants__inventory__quantity", filter=Q(variants__is_active=True)),
        variant_count=Count("variants", distinct=True),
    )
    if q:
        by_sku = ProductVariant.objects.filter(sku__icontains=q).values("product_id")  # subquery: a join here would inflate the stock sum
        qs = qs.filter(Q(name__icontains=q) | Q(keywords__icontains=q) | Q(pk__in=by_sku))
    if status:
        qs = qs.filter(status=status)
    if category_id.isdigit():
        category = Category.objects.filter(pk=category_id).first()
        if category:
            qs = qs.filter(category_id__in=category.get_descendant_ids())
    if stock == "out":
        qs = qs.filter(Q(stock__isnull=True) | Q(stock=0))
    elif stock == "in":
        qs = qs.filter(stock__gt=0)
    elif stock == "low":
        low = Inventory.objects.filter(variant__is_active=True, quantity__gt=0, quantity__lte=F("low_stock_threshold"))
        qs = qs.filter(pk__in=low.values("variant__product_id"))
    return page(request, "dashboard/products.html", "products", page_obj=paginate(request, qs), q=q, status=status, stock=stock,
                category_id=category_id, categories=Category.objects.select_related("parent"), qs=keep_query(request))


def _edit_context(product, **forms):
    ctx = {"product": product}
    if product and product.pk:
        variants = product.variants.select_related("size", "colour", "inventory")
        ctx.update(
            images=product.images.select_related("colour"),
            image_form=forms.get("image_form") or ProductImagesForm(),
            variant_form=forms.get("variant_form") or VariantCreateForm(),
            variant_formset=forms.get("variant_formset") or VariantFormSet(queryset=variants),
            variants=variants,
        )
    return ctx


@dashboard_required("catalogue")
def product_edit(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"{saved.name} saved." if product else f"{saved.name} created. Now add images and variants.")
        return redirect("dashboard:product_edit", pk=saved.pk)
    return page(request, "dashboard/product_form.html", "products", form=form, **_edit_context(product))


def _back(product, anchor):
    return redirect(f"/dashboard/products/{product.pk}/#{anchor}")


@dashboard_required("catalogue")
@require_POST
def product_images(request, pk):
    product = get_object_or_404(Product, pk=pk)
    action = request.POST.get("action", "upload")
    if action == "upload":
        form = ProductImagesForm(request.POST, request.FILES)
        if not form.is_valid():
            return page(request, "dashboard/product_form.html", "products", form=ProductForm(instance=product),
                        **_edit_context(product, image_form=form))
        with transaction.atomic():
            has_primary = product.images.filter(is_primary=True).exists()
            position = product.images.count()
            for upload in form.cleaned_data["images"]:
                ProductImage.objects.create(
                    product=product, image=upload, colour=form.cleaned_data["colour"], position=position,
                    is_primary=not has_primary, alt_text=product.name,
                )
                has_primary, position = True, position + 1
        messages.success(request, "Images added.")
    else:
        image_id = request.POST.get("image", "")
        image = get_object_or_404(ProductImage, pk=image_id if image_id.isdigit() else 0, product=product)
        with transaction.atomic():
            if action == "primary":
                product.images.exclude(pk=image.pk).update(is_primary=False)
                image.is_primary = True
                image.save(update_fields=["is_primary", "updated_at"])
                messages.success(request, "Main image changed.")
            elif action == "delete":
                was_primary = image.is_primary
                image.delete()
                if was_primary:
                    nxt = product.images.first()
                    if nxt:
                        nxt.is_primary = True
                        nxt.save(update_fields=["is_primary", "updated_at"])
                messages.success(request, "Image removed.")
            elif action == "alt":
                alt_form = ImageAltForm(request.POST, instance=image)
                if alt_form.is_valid():
                    alt_form.save()
                    messages.success(request, "Image details saved.")
    return _back(product, "images")


@dashboard_required("catalogue")
@require_POST
def variants_create(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = VariantCreateForm(request.POST)
    if not form.is_valid():
        return page(request, "dashboard/product_form.html", "products", form=ProductForm(instance=product),
                    **_edit_context(product, variant_form=form))
    d = form.cleaned_data
    created, skipped = services.create_variants(
        product, d["sizes"], d["colours"] or [Colour.standard()], price_override=d["price_override"], initial_stock=d["initial_stock"] or 0, user=request.user
    )
    msg = f"{created} variant{'s' if created != 1 else ''} added."
    if skipped:
        msg += f" {skipped} already existed."
    messages.success(request, msg)
    return _back(product, "variants")


@dashboard_required("catalogue")
@require_POST
def variants_save(request, pk):
    product = get_object_or_404(Product, pk=pk)
    formset = VariantFormSet(request.POST, queryset=product.variants.select_related("size", "colour", "inventory"))
    if not formset.is_valid():
        return page(request, "dashboard/product_form.html", "products", form=ProductForm(instance=product),
                    **_edit_context(product, variant_formset=formset))
    formset.save()
    messages.success(request, "Variants saved.")
    return _back(product, "variants")


@dashboard_required("catalogue")
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = product.name
    product.delete()  # order lines keep their own snapshot, so sales history is untouched
    messages.success(request, f"{name} deleted. Past orders keep their records.")
    return redirect("dashboard:products")
