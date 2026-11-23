"""
Apply an updates file from ``build_client_updates`` without resetting
anything (safe on a live instance). See core/client_updates.py.

Usage: python manage.py apply_client_updates ../client_data/updates.json.gz
"""
import gzip
import json

from django.core.management.base import BaseCommand

from core.client_updates import UpdateApplier


class Command(BaseCommand):
    help = "Apply incremental client updates (no reset)."

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **opts):
        with gzip.open(opts['path'], 'rt', encoding='utf-8') as fh:
            updates = json.load(fh)
        UpdateApplier(updates, log=self.stdout.write).run()
