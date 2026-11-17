import csv
from datetime import timedelta
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone

from .. import reports as report_defs
from .. import rules
from ..access import dashboard_required
from .common import clean_choice, keep_query, page

HTML_ROW_LIMIT = 200


def _show(cell):
    """Money cells (Decimal) read as naira on screen; counts stay plain."""
    if isinstance(cell, Decimal):
        return f"₦{cell:,.0f}" if cell == cell.to_integral_value() else f"₦{cell:,.2f}"
    return cell


def csv_response(filename, columns, rows):
    # utf-8-sig so Excel opens naira signs and accents correctly
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow([rules.csv_safe(c) for c in columns])
    for row in rows:
        writer.writerow([rules.csv_safe(cell) for cell in row])
    return response


@dashboard_required("reports")
def reports(request):
    kind = clean_choice(request.GET.get("report"), set(report_defs.REPORTS), "sales")
    today = timezone.localdate()
    start_date, end_date, note = rules.parse_range(request.GET.get("from"), request.GET.get("to"), today)
    start, end = report_defs.bounds(start_date, end_date)
    data = report_defs.REPORTS[kind](start, end)
    if request.GET.get("export") == "csv":
        stamp = f"{start_date}-to-{end_date}" if data["uses_range"] else str(today)
        return csv_response(f"avelle-{kind}-{stamp}.csv", data["columns"], data["rows"])
    total_rows = len(data["rows"])
    data["rows"] = [[_show(cell) for cell in row] for row in data["rows"][:HTML_ROW_LIMIT]]  # the CSV above keeps raw numbers
    presets = [(label, (today - timedelta(days=d - 1)).isoformat()) for label, d in (("7 days", 7), ("30 days", 30), ("90 days", 90))]
    return page(request, "dashboard/reports.html", "reports", data=data, kind=kind, tabs=report_defs.TABS, start=start_date, end=end,
                range_note=note, total_rows=total_rows, truncated=total_rows > HTML_ROW_LIMIT, presets=presets, today=today,
                export_qs=keep_query(request, drop=("page", "export")))
