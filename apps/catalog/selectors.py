"""Read-side queries for the storefront: filtering, facets, search and sorting.

One entry point, `search_products(params)`, takes request.GET and returns a
`ShopResult` with the page of products, facet options with live counts, active
filter chips and the category navigation. Nothing here writes to the database.

Design notes
- All variant conditions (size, colour, in stock) are combined in ONE Exists() so
  "size M in Olive" means a single variant that is both, not any M and any Olive.
- Each facet's counts are computed against the other filters but NOT its own, so
  choosing "M" does not make "L" show zero.
- Effective price is Coalesce(discount_price, price), the price a customer pays.
"""
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Case, Count, DecimalField, Exists, F, IntegerField, Max, Min, OuterRef, Q, Value, When
from django.db.models.functions import Coalesce

from apps.catalog.models import Brand, Category, Colour, Product, ProductVariant, Size

SORTS = {
    "newest": ("Newest", (F("published_at").desc(nulls_last=True), "-created_at", "-pk")),
    "price_asc": ("Price: low to high", ("effective_price", "-pk")),
    "price_desc": ("Price: high to low", ("-effective_price", "-pk")),
    "discount": ("Biggest reduction", ("-discount_amount", "-pk")),
    "name": ("Name: A to Z", ("name", "pk")),
}
RELEVANCE = ("Most relevant", ("-relevance", "-pk"))
MAX_LIST = 12  # cap on multi-value params, protects the query from abuse


def storefront_products():
    """Published products with what the cards need, annotated with stock availability."""
    in_stock = ProductVariant.objects.filter(
        product=OuterRef("pk"), is_active=True, inventory__quantity__gt=0
    )
    return (
        Product.objects.published()
        .select_related("brand", "category")
        .prefetch_related("images")
        .annotate(in_stock=Exists(in_stock))
    )


# ---------------------------------------------------------------------------
# Category tree
# ---------------------------------------------------------------------------
class CategoryTree:
    """Active categories loaded once per request and navigated in memory."""

    def __init__(self):
        self.all = list(Category.objects.filter(is_active=True).order_by("position", "name"))
        self.by_id = {c.pk: c for c in self.all}
        self.children = {}
        for c in self.all:
            self.children.setdefault(c.parent_id, []).append(c)
        self.roots = self.children.get(None, [])

    def root_by_slug(self, slug):
        return next((c for c in self.roots if c.slug == slug), None)

    def child_by_slug(self, parent, slug):
        return next((c for c in self.children.get(parent.pk, []) if c.slug == slug), None) if parent else None

    def descendant_ids(self, category):
        ids, stack = [], [category]
        while stack:
            node = stack.pop()
            ids.append(node.pk)
            stack.extend(self.children.get(node.pk, []))
        return ids

    def root_of(self, category_id):
        node = self.by_id.get(category_id)
        while node and node.parent_id:
            node = self.by_id.get(node.parent_id)
        return node


# ---------------------------------------------------------------------------
# Filters parsed from the query string
# ---------------------------------------------------------------------------
def _decimal(value):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number >= 0 else None


def _ints(values):
    out = []
    for v in values[:MAX_LIST]:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class ShopFilters:
    q: str = ""
    category: str = ""
    type: str = ""
    sizes: list = field(default_factory=list)      # Size ids
    colours: list = field(default_factory=list)    # Colour ids
    brands: list = field(default_factory=list)     # Brand slugs
    price_min: Decimal = None
    price_max: Decimal = None
    new: bool = False
    featured: bool = False
    sale: bool = False
    in_stock: bool = False
    sort: str = ""
    page: int = 1

    @classmethod
    def from_params(cls, params):
        flag = lambda key: params.get(key) in ("1", "true", "on")
        try:
            page = max(1, int(params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        pmin, pmax = _decimal(params.get("min", "")), _decimal(params.get("max", ""))
        if pmin is not None and pmax is not None and pmin > pmax:
            pmin, pmax = pmax, pmin
        q = " ".join(params.get("q", "").split())[:80]
        sort = params.get("sort", "")
        if sort not in SORTS:
            sort = ""
        return cls(
            q=q,
            category=params.get("category", "").strip()[:120],
            type=params.get("type", "").strip()[:120],
            sizes=_ints(params.getlist("size")),
            colours=_ints(params.getlist("colour")),
            brands=[b.strip()[:120] for b in params.getlist("brand")[:MAX_LIST] if b.strip()],
            price_min=pmin, price_max=pmax,
            new=flag("new"), featured=flag("featured"), sale=flag("sale"), in_stock=flag("in_stock"),
            sort=sort, page=page,
        )

    @property
    def effective_sort(self):
        return self.sort or ("relevance" if self.q else "newest")

    def pairs(self, drop=(), page=None):
        """Query-string pairs for the current filters. `drop` is a set of keys or (key, value)."""
        out = []

        def add(key, value):
            if key in drop or (key, str(value)) in drop:
                return
            out.append((key, value))

        if self.q: add("q", self.q)
        if self.category: add("category", self.category)
        if self.type and self.category: add("type", self.type)
        for v in self.sizes: add("size", v)
        for v in self.colours: add("colour", v)
        for v in self.brands: add("brand", v)
        if self.price_min is not None: add("min", self.price_min.normalize())
        if self.price_max is not None: add("max", self.price_max.normalize())
        for key in ("new", "featured", "sale", "in_stock"):
            if getattr(self, key): add(key, 1)
        if self.sort: add("sort", self.sort)
        if page and page > 1: out.append(("page", page))
        return out

    def query_string(self, drop=(), page=None):
        qs = urlencode(self.pairs(drop, page))
        return f"?{qs}" if qs else "?"

    def href(self, **changes):
        """Query string with some fields replaced; always resets to page 1."""
        return replace(self, page=1, **changes).query_string()

    @property
    def active_count(self):
        return len(self.sizes) + len(self.colours) + len(self.brands) + sum(
            [bool(self.price_min is not None or self.price_max is not None), self.new, self.featured, self.sale, self.in_stock]
        )


# ---------------------------------------------------------------------------
# Applying filters
# ---------------------------------------------------------------------------
def with_effective_price(qs):
    return qs.annotate(
        effective_price=Coalesce("discount_price", "price", output_field=DecimalField(max_digits=12, decimal_places=2)),
        discount_amount=Case(
            When(discount_price__isnull=False, then=F("price") - F("discount_price")),
            default=Value(Decimal("0")), output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )


def _search_q(text):
    """Every word must match somewhere (name, brand, category, descriptions, keywords)."""
    cond = Q()
    for word in text.split()[:6]:
        cond &= (
            Q(name__icontains=word) | Q(brand__name__icontains=word) | Q(category__name__icontains=word)
            | Q(category__parent__name__icontains=word) | Q(short_description__icontains=word)
            | Q(keywords__icontains=word)
        )
    return cond


def variant_conditions(f, skip=()):
    cond = Q(is_active=True)
    used = False
    if f.sizes and "size" not in skip:
        cond &= Q(size_id__in=f.sizes); used = True
    if f.colours and "colour" not in skip:
        cond &= Q(colour_id__in=f.colours); used = True
    if f.in_stock and "in_stock" not in skip:
        cond &= Q(inventory__quantity__gt=0); used = True
    return cond, used


def apply_filters(qs, f, tree, skip=()):
    """Return qs narrowed by the filters, ignoring any facet named in `skip`."""
    if f.q and "q" not in skip:
        qs = qs.filter(_search_q(f.q))

    if "category" not in skip:
        root = tree.root_by_slug(f.category) if f.category else None
        if f.category and root is None:
            return qs.none()
        if root:
            target = tree.child_by_slug(root, f.type) if f.type else None
            if f.type and target is None:
                return qs.none()
            qs = qs.filter(category_id__in=tree.descendant_ids(target or root))

    if f.brands and "brand" not in skip:
        qs = qs.filter(brand__slug__in=f.brands)

    cond, used = variant_conditions(f, skip)
    if used:
        qs = qs.filter(Exists(ProductVariant.objects.filter(cond, product=OuterRef("pk"))))

    if "price" not in skip:
        if f.price_min is not None:
            qs = qs.filter(effective_price__gte=f.price_min)
        if f.price_max is not None:
            qs = qs.filter(effective_price__lte=f.price_max)

    if f.new and "new" not in skip:
        qs = qs.filter(is_new_arrival=True)
    if f.featured and "featured" not in skip:
        qs = qs.filter(is_featured=True)
    if f.sale and "sale" not in skip:
        qs = qs.filter(discount_price__isnull=False)
    return qs


def apply_sort(qs, f):
    key = f.effective_sort
    if key == "relevance":
        q = f.q
        qs = qs.annotate(relevance=Case(
            When(name__iexact=q, then=Value(4)),
            When(name__istartswith=q, then=Value(3)),
            When(name__icontains=q, then=Value(2)),
            default=Value(1), output_field=IntegerField(),
        ))
        return qs.order_by(*RELEVANCE[1])
    return qs.order_by(*SORTS[key][1])


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------
def _variant_facet(base_qs, f, tree, field_name):
    """Counts of distinct products per size/colour, honouring every other filter."""
    products = apply_filters(base_qs, f, tree, skip={field_name})
    variants = ProductVariant.objects.filter(is_active=True, product__in=products.values("pk"))
    if f.in_stock:
        variants = variants.filter(inventory__quantity__gt=0)
    other = "colours" if field_name == "size" else "sizes"
    if other == "colours" and f.colours:
        variants = variants.filter(colour_id__in=f.colours)
    if other == "sizes" and f.sizes:
        variants = variants.filter(size_id__in=f.sizes)
    rows = variants.values(f"{field_name}_id").annotate(n=Count("product", distinct=True))
    return {row[f"{field_name}_id"]: row["n"] for row in rows}


def build_facets(base_qs, f, tree):
    size_counts = _variant_facet(base_qs, f, tree, "size")
    colour_counts = _variant_facet(base_qs, f, tree, "colour")

    # Brand counts: everything except the brand filter
    brand_rows = (
        apply_filters(base_qs, f, tree, skip={"brand"})
        .exclude(brand__isnull=True)
        .values("brand__slug", "brand__name")
        .annotate(n=Count("pk", distinct=True))
        .order_by("brand__name")
    )
    brand_options = [
        {"value": r["brand__slug"], "label": r["brand__name"], "count": r["n"], "selected": r["brand__slug"] in f.brands}
        for r in brand_rows
    ]
    # Keep selected brands visible even when their count dropped to zero
    seen = {b["value"] for b in brand_options}
    for brand in Brand.objects.filter(slug__in=f.brands).exclude(slug__in=seen):
        brand_options.append({"value": brand.slug, "label": brand.name, "count": 0, "selected": True})

    # Sizes: only sizes that exist for the current category scope, grouped
    scope = apply_filters(base_qs, f, tree, skip={"size", "colour", "brand", "price", "in_stock", "new", "featured", "sale", "q"})
    scoped_sizes = set(ProductVariant.objects.filter(is_active=True, product__in=scope.values("pk")).values_list("size_id", flat=True))
    scoped_sizes |= set(f.sizes)
    groups = {}
    for size in Size.objects.filter(pk__in=scoped_sizes).order_by("group", "sort_order", "name"):
        groups.setdefault(size.get_group_display(), []).append({
            "value": size.pk, "label": size.name, "count": size_counts.get(size.pk, 0), "selected": size.pk in f.sizes,
        })
    size_groups = [{"label": label, "options": options} for label, options in groups.items()]

    scoped_colours = set(ProductVariant.objects.filter(is_active=True, product__in=scope.values("pk")).values_list("colour_id", flat=True))
    scoped_colours |= set(f.colours)
    colour_options = [
        {"value": c.pk, "label": c.name, "hex": c.hex_code, "count": colour_counts.get(c.pk, 0), "selected": c.pk in f.colours}
        for c in Colour.objects.filter(pk__in=scoped_colours).order_by("sort_order", "name")
    ]

    bounds = apply_filters(base_qs, f, tree, skip={"price"}).aggregate(low=Min("effective_price"), high=Max("effective_price"))

    return {
        "sizes": size_groups,
        "colours": colour_options,
        "brands": brand_options,
        "price": {
            "low": int(bounds["low"] or 0), "high": int(bounds["high"] or 0),
            "min": f.price_min, "max": f.price_max,
        },
    }


def type_options(base_qs, f, tree):
    """Subcategory choices under the selected root, with counts under the other filters."""
    root = tree.root_by_slug(f.category) if f.category else None
    if not root:
        return []
    scoped = apply_filters(base_qs, f, tree, skip={"category"}).filter(category_id__in=tree.descendant_ids(root))
    per_category = dict(scoped.values_list("category_id").annotate(n=Count("pk")))
    options = []
    for child in tree.children.get(root.pk, []):
        count = sum(per_category.get(cid, 0) for cid in tree.descendant_ids(child))
        options.append({"slug": child.slug, "name": child.name, "count": count, "selected": child.slug == f.type,
                        "href": f.href(type="" if child.slug == f.type else child.slug)})
    return options


def collection_tabs(base_qs, f, tree):
    scoped = apply_filters(base_qs, f, tree, skip={"category"})
    per_category = dict(scoped.values_list("category_id").annotate(n=Count("pk")))
    tabs = []
    for root in tree.roots:
        count = sum(per_category.get(cid, 0) for cid in tree.descendant_ids(root))
        tabs.append({"slug": root.slug, "name": root.name, "count": count, "selected": root.slug == f.category,
                     "href": f.href(category=root.slug, type="")})
    return tabs, sum(t["count"] for t in tabs), f.href(category="", type="")


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------
def build_chips(f, tree, facets, root, target):
    chips = []

    def chip(label, drop):
        chips.append({"label": label, "href": f.query_string(drop=drop)})

    if f.q: chip(f"“{f.q}”", {"q"})
    if root and f.category: chip(root.name, {"category", "type"})
    if target and f.type: chip(target.name, {"type"})
    size_labels = {o["value"]: o["label"] for g in facets["sizes"] for o in g["options"]}
    for sid in f.sizes: chip(f"Size {size_labels.get(sid, sid)}", {("size", str(sid))})
    colour_labels = {o["value"]: o["label"] for o in facets["colours"]}
    for cid in f.colours: chip(colour_labels.get(cid, "Colour"), {("colour", str(cid))})
    brand_labels = {o["value"]: o["label"] for o in facets["brands"]}
    for slug in f.brands: chip(brand_labels.get(slug, slug), {("brand", slug)})
    if f.price_min is not None or f.price_max is not None:
        lo = f"{settings.CURRENCY_SYMBOL}{int(f.price_min):,}" if f.price_min is not None else "Any"
        hi = f"{settings.CURRENCY_SYMBOL}{int(f.price_max):,}" if f.price_max is not None else "Any"
        chip(f"{lo} – {hi}", {"min", "max"})
    for key, label in (("new", "New arrivals"), ("featured", "Featured"), ("sale", "On sale"), ("in_stock", "In stock")):
        if getattr(f, key): chip(label, {key})
    return chips


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
@dataclass
class ShopResult:
    filters: ShopFilters
    page: object
    total: int
    facets: dict
    chips: list
    tabs: list
    all_count: int
    all_href: str
    types: list
    root: object
    target: object
    sorts: list
    heading: str
    next_query: str = ""
    prev_query: str = ""
    page_numbers: list = field(default_factory=list)


def search_products(params):
    f = ShopFilters.from_params(params)
    tree = CategoryTree()
    base = with_effective_price(storefront_products())

    root = tree.root_by_slug(f.category) if f.category else None
    target = tree.child_by_slug(root, f.type) if (root and f.type) else None

    qs = apply_sort(apply_filters(base, f, tree), f)
    paginator = Paginator(qs, settings.PRODUCTS_PER_PAGE)
    try:
        page = paginator.page(f.page)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
        f.page = page.number

    facets = build_facets(base, f, tree)
    tabs, all_count, all_href = collection_tabs(base, f, tree)
    types = type_options(base, f, tree)
    chips = build_chips(f, tree, facets, root, target)

    if f.q:
        heading = f"Results for “{f.q}”"
    elif target:
        heading = f"{root.name}’s {target.name}" if root.name in ("Men", "Women") else target.name
    elif root:
        heading = root.name
    elif f.new and not f.sale and not f.featured:
        heading = "New arrivals"
    elif f.sale and not f.new and not f.featured:
        heading = "Sale"
    elif f.featured and not f.new and not f.sale:
        heading = "Featured"
    else:
        heading = "Shop all"

    sorts = [{"value": k, "label": v[0], "selected": k == f.effective_sort} for k, v in SORTS.items()]
    if f.q:
        sorts.insert(0, {"value": "relevance", "label": RELEVANCE[0], "selected": f.effective_sort == "relevance"})

    # Compact page list: 1 … 4 5 6 … 12
    numbers, n, last = [], page.number, paginator.num_pages
    for p in sorted({1, last, n - 1, n, n + 1}):
        if 1 <= p <= last:
            if numbers and numbers[-1] is not None and p - numbers[-1]["n"] > 1:
                numbers.append(None)
            numbers.append({"n": p, "href": f.query_string(page=p)})

    return ShopResult(
        filters=f, page=page, total=paginator.count, facets=facets, chips=chips, tabs=tabs, all_count=all_count, all_href=all_href,
        types=types, root=root, target=target, sorts=sorts, heading=heading,
        next_query=f.query_string(page=page.number + 1) if page.has_next() else "",
        prev_query=f.query_string(page=page.number - 1) if page.has_previous() else "",
        page_numbers=numbers,
    )


def related_products(product, limit=4):
    """Same category first, then same root collection, never the product itself."""
    qs = storefront_products().exclude(pk=product.pk)
    picked = list(qs.filter(category_id=product.category_id)[:limit])
    if len(picked) < limit and product.category_id:
        tree = CategoryTree()
        root = tree.root_of(product.category_id)
        if root:
            exclude = [p.pk for p in picked]
            picked += list(qs.filter(category_id__in=tree.descendant_ids(root)).exclude(pk__in=exclude)[: limit - len(picked)])
    return picked


def suggest(text, limit=6):
    """Fast typeahead: product matches plus matching categories."""
    text = " ".join(text.split())[:80]
    if len(text) < 2:
        return {"products": [], "categories": []}
    products = list(
        with_effective_price(storefront_products()).filter(_search_q(text)).order_by("-is_featured", "name")[:limit]
    )
    tree = CategoryTree()
    lowered = text.lower()
    categories = []
    for c in tree.all:
        if lowered in c.name.lower():
            root = tree.root_of(c.pk)
            if c.parent_id is None:
                categories.append({"name": c.name, "url": f"/shop/?category={c.slug}"})
            else:
                categories.append({"name": f"{root.name} · {c.name}", "url": f"/shop/?category={root.slug}&type={c.slug}"})
    return {"products": products, "categories": categories[:4]}
