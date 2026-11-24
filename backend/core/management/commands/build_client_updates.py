"""
Read the distributor's follow-up files and answers into a git-ignored
updates file (see core/client_updates.py for what gets applied).

Usage:
    python manage.py build_client_updates \
        --source "../artifacts/mumtaz and co response " \
        --manual ../client_data/manual_inputs.json \
        --out ../client_data/updates.json.gz
"""
import gzip
import json
import os

from django.core.management.base import BaseCommand

from core.client_updates import read_expenses, read_targets


class Command(BaseCommand):
    help = "Build a client updates file (inactive DRs, renames, targets, expenses)."

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True)
        parser.add_argument('--manual', required=True)
        parser.add_argument('--out', required=True)

    def handle(self, *args, **opts):
        with open(opts['manual'], encoding='utf-8') as fh:
            manual = json.load(fh).get('updates', {})
        updates = {
            'kind': 'updates',
            'inactive_drs': manual.get('inactive_drs', []),
            'dr_renames': manual.get('dr_renames', {}),
            'target_aliases': manual.get('target_aliases', {}),
            'dr_channels': manual.get('dr_channels', {}),
            'expense_accounts': manual.get('expense_accounts', []),
            'expense_labels': manual.get('expense_labels', {}),
        }
        for spec in manual.get('targets', []):
            rows = read_targets(os.path.join(opts['source'], spec['file']))
            updates['targets'] = {'months': spec['months'], 'rows': rows}
        for spec in manual.get('expenses', []):
            rows = read_expenses(os.path.join(opts['source'], spec['file']))
            updates['expenses'] = {'month': spec['month'], 'rows': rows}
        with gzip.open(opts['out'], 'wt', encoding='utf-8') as fh:
            json.dump(updates, fh)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {opts['out']}: {len(updates.get('targets', {}).get('rows', []))} target rows, "
            f"{len(updates.get('expenses', {}).get('rows', []))} expense lines."
        ))
