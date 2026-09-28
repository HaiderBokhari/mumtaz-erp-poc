"""
Post accounting entries for any PurchaseOrder/SalesOrder that reached
RECEIVED/CONFIRMED before the accounting module existed (or before a given
deploy added new auto-posting logic). Purely additive and idempotent: it
only ever adds a JournalEntry for a PO/SO that doesn't already have one
with the matching source+reference, never deletes or re-runs stock
movement — safe to run on every boot, unlike a full reseed/flush.

Usage: python manage.py backfill_accounting_entries
"""
from django.core.management.base import BaseCommand

from accounting.models import JournalEntry
from distribution.models import SalesOrder
from purchasing.models import PurchaseOrder


class Command(BaseCommand):
    help = 'Post accounting entries for already-received POs / already-confirmed SOs that predate the accounting module.'

    def handle(self, *args, **options):
        posted_po = 0
        already_posted_po_refs = set(
            JournalEntry.objects.filter(source=JournalEntry.SOURCE_PURCHASE).values_list('reference', flat=True)
        )
        for po in PurchaseOrder.objects.filter(status=PurchaseOrder.STATUS_RECEIVED).exclude(po_number__in=already_posted_po_refs):
            po.post_accounting_entry(user=po.created_by)
            posted_po += 1

        posted_so = 0
        already_posted_so_refs = set(
            JournalEntry.objects.filter(source=JournalEntry.SOURCE_SALE).values_list('reference', flat=True)
        )
        for so in SalesOrder.objects.filter(status=SalesOrder.STATUS_CONFIRMED).exclude(so_number__in=already_posted_so_refs):
            so.post_accounting_entry(user=so.created_by)
            posted_so += 1

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled accounting entries for {posted_po} purchase order(s) and {posted_so} sales order(s).'
        ))
