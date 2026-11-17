"""
Load a bundle made by ``build_client_bundle`` — see core/client_bundle.py
for what it loads and what it resets.

Usage: python manage.py load_client_bundle ../client_data/bundle.json.gz
"""
import gzip
import json

from django.core.management.base import BaseCommand

from core.client_bundle import BundleLoader


class Command(BaseCommand):
    help = "Reset business data to the real Mumtaz & Co data in a client bundle."

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to bundle.json.gz')

    def handle(self, *args, **opts):
        with gzip.open(opts['path'], 'rt', encoding='utf-8') as fh:
            bundle = json.load(fh)
        BundleLoader(bundle, log=self.stdout.write).run()
