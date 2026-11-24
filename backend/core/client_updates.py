"""
Incremental client updates: answers and files the distributor sends after
the main bundle was loaded. Unlike ``BundleLoader`` this never resets
anything, so it can run on a live instance where staff are already keying
in data. Every step is idempotent (safe to apply twice).

What it applies (team answers, 23 Nov 2026):
- DR devices permanently discontinued in BIZOM are made inactive, so they
  drop out of the daily entry screens (history stays).
- Renames, e.g. DR28 is the wholesale mandi device, not "Shop Sale".
- Monthly DR targets from their "TARGET OCT AND NOV" sheet, matched to DRs
  by name (names the sheet spells differently are listed, not guessed).
- Each DR's own sales channel (DD / VDD / MANDI / SHOP), and the channel
  tag on actual-sale rows that have none yet.
- One month of real expenses from their Expences sheet, replacing the
  seeded running costs (the seeded entries are reversed, not deleted).
  Lines that are a family member's drawings rather than business costs go
  to their own equity account (``expense_accounts``), one per person, and
  lines posted before such a mapping existed are reclassified.

Real client data never goes into git: ``build_client_updates`` reads their
files into a git-ignored ``updates.json.gz`` which is applied with
``apply_client_updates`` locally, or uploaded to the owner-only
``/api/admin/client-bundle/`` like the main bundle.
"""
import calendar
import datetime
import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from accounting.models import ChartOfAccount, JournalEntry, Party
from catalog.models import Channel
from distribution.models import ActualSale, SalesTarget
from hr.models import Employee

D0 = Decimal('0')
SEEDED_EXPENSE_REF = 'EXP-SEEDED'
SEEDED_EXPENSE_REVERSAL_REF = 'EXP-SEEDED-REV'

# Lines on their expense sheet that are not business running costs.
DRAWINGS_ITEMS = {'owner salary', 'madam all persnol expenses', 'madam all personal expenses'}
# DR/staff salaries are already posted from the pay structure (hr.SalaryPayment).
PAYROLL_ITEMS = {'staff salary'}


def norm(name):
    return re.sub(r'[^a-z]', '', str(name or '').lower())


# -- reading their files ------------------------------------------------------------

def read_targets(path):
    """TARGET OCT AND NOV.xlsx: rows of DR | FSO | TARGET | ACH | %."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows, header = [], None
    for values in ws.iter_rows(values_only=True):
        cells = [str(v).strip() if v is not None else '' for v in values]
        if header is None:
            if 'DR' in cells and 'TARGET' in cells:
                header = {name: i for i, name in enumerate(cells) if name}
            continue
        name = cells[header['DR']]
        if not name or name.upper() == 'TOTAL':
            if name.upper() == 'TOTAL':
                break
            continue
        raw = values[header['TARGET']]
        rows.append({
            'name': name,
            'fso': cells[header.get('FSO', header['DR'] + 1)],
            'target_m': float(raw) if isinstance(raw, (int, float)) else None,
        })
    return rows


def read_expenses(path):
    """Their monthly Expences sheet: section rows (A, B, ...), item rows with one column per day."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    day_cols, section, out = None, '', []
    for values in ws.iter_rows(values_only=True):
        cells = list(values)
        first = str(cells[0]).strip() if cells[0] is not None else ''
        label = str(cells[1]).strip() if len(cells) > 1 and cells[1] is not None else ''
        if day_cols is None:
            if first.upper().startswith('SR'):
                day_cols = {}
                for i, v in enumerate(cells):
                    if isinstance(v, (int, float)) and 1 <= v <= 31 and int(v) not in day_cols.values():
                        day_cols[i] = int(v)
            continue
        if first.upper().startswith('GRAND'):
            section = 'Owner'
            continue
        if re.fullmatch(r'[A-Z]', first) and label:
            section = label
            continue
        if not label or label.lower() == 'total':
            continue
        for i, day in day_cols.items():
            v = cells[i] if i < len(cells) else None
            if isinstance(v, (int, float)) and v:
                out.append({'day': day, 'section': section, 'item': label, 'amount': round(float(v), 2)})
    return out


# -- applying -------------------------------------------------------------------------

class UpdateApplier:
    def __init__(self, updates, log=print):
        self.u = updates
        self.log = log
        self.owner = User.objects.filter(is_superuser=True).order_by('id').first()
        self.result = {}

    @transaction.atomic
    def run(self):
        self._inactive()
        self._renames()
        self._channels()
        self._targets()
        self._expenses()
        self.log('Client updates applied.')
        return self.result

    def _dr(self, code):
        return User.objects.select_related('profile').filter(profile__dr_code=code).first()

    def _inactive(self):
        codes = self.u.get('inactive_drs', [])
        n = User.objects.filter(profile__dr_code__in=codes, is_active=True).update(is_active=False)
        self.log(f'Inactive DRs: {", ".join(codes) or "none"} ({n} changed)')
        self.result['inactive_drs'] = codes

    def _renames(self):
        for code, name in self.u.get('dr_renames', {}).items():
            user = self._dr(code)
            if user is None or user.first_name == name:
                continue
            old_party = f'DR {code} - {user.get_full_name() or user.username}'
            user.first_name, user.last_name = name, ''
            user.save(update_fields=['first_name', 'last_name'])
            Employee.objects.filter(user=user).update(full_name=name)
            Party.objects.filter(name=old_party).update(name=f'DR {code} - {name}')
            self.log(f'Renamed {code} to {name}')

    def _channels(self):
        from accounts.models import UserProfile
        from distribution.channels import backfill_sale_channels

        for profile in UserProfile.objects.filter(user__groups__name='Distribution Representative', sales_channel=''):
            grade = getattr(Employee.objects.filter(user_id=profile.user_id).select_related('pay_grade').first(),
                            'pay_grade', None)
            profile.sales_channel = Channel.TYPE_VDD if grade and grade.name == 'VDD' else Channel.TYPE_DD
            profile.save(update_fields=['sales_channel'])
        for code, channel in self.u.get('dr_channels', {}).items():
            UserProfile.objects.filter(dr_code=code).exclude(sales_channel=channel).update(sales_channel=channel)
            ActualSale.objects.filter(dr__profile__dr_code=code).exclude(
                channel_type=channel).filter(bucket='RETAIL').update(channel_type=channel)
        n = backfill_sale_channels()
        self.log(f'Channels: {len(self.u.get("dr_channels", {}))} DR overrides, {n} sale rows tagged')

    def _targets(self):
        targets = self.u.get('targets')
        if not targets:
            return
        channel = Channel.objects.filter(
            channel_type=Channel.TYPE_DD, filer_status=Channel.NON_FILER).order_by('id').first()
        aliases = {norm(k): v for k, v in self.u.get('target_aliases', {}).items()}
        drs = {}
        for user in User.objects.filter(groups__name='Distribution Representative').select_related('profile'):
            drs.setdefault(norm(user.first_name), user)
            drs[norm(user.profile.dr_code)] = user
        matched, unmatched, skipped_inactive = [], [], []
        for row in targets['rows']:
            if row['target_m'] is None:
                continue
            user = drs.get(norm(aliases.get(norm(row['name']), ''))) or drs.get(norm(row['name']))
            if user is None:
                unmatched.append(row['name'])
                continue
            if not user.is_active:
                skipped_inactive.append(row['name'])
                continue
            for year, month in targets['months']:
                SalesTarget.objects.update_or_create(
                    dr=user, channel=channel, year=year, month=month,
                    defaults={'target_volume_m': Decimal(str(row['target_m']))},
                )
            matched.append(row['name'])
        self.log(f'Targets: {len(matched)} DRs set for {targets["months"]}; '
                 f'not matched: {", ".join(unmatched) or "none"}; discontinued: {", ".join(skipped_inactive) or "none"}')
        self.result['targets'] = {'matched': matched, 'unmatched': unmatched, 'discontinued': skipped_inactive}

    def _expenses(self):
        exp = self.u.get('expenses')
        if not exp:
            return
        year, month = map(int, exp['month'].split('-'))
        reference = f'EXP-{year}{month:02d}'
        special = self._expense_accounts()
        if JournalEntry.objects.filter(reference=reference).exists():
            self._reclassify(reference, special)
            self.log(f'Expenses for {exp["month"]} already posted.')
            return
        # Their real figures replace the seeded estimates: reverse the seeded entries.
        if not JournalEntry.objects.filter(reference=SEEDED_EXPENSE_REVERSAL_REF).exists():
            for entry in JournalEntry.objects.filter(reference=SEEDED_EXPENSE_REF).prefetch_related('lines__account'):
                JournalEntry.create_posted(
                    source=JournalEntry.SOURCE_VOUCHER, date=entry.date, reference=SEEDED_EXPENSE_REVERSAL_REF,
                    narration=f'Reversal: {entry.narration} (replaced by real expenses)', created_by=self.owner,
                    lines=[{'account': line.account, 'debit': line.credit, 'credit': line.debit, 'party': line.party}
                           for line in entry.lines.all()],
                )
        last_day = calendar.monthrange(year, month)[1]
        totals = {'expense': D0, 'drawings': D0, 'payroll_skipped': D0}
        for row in exp['rows']:
            item = norm(row['item'])
            amount = Decimal(str(row['amount']))
            if item in {norm(i) for i in PAYROLL_ITEMS}:
                totals['payroll_skipped'] += amount
                continue
            drawings = item in special or item in {norm(i) for i in DRAWINGS_ITEMS}
            account = special.get(item) or (ChartOfAccount.OWNER_EQUITY if drawings else ChartOfAccount.GENERAL_EXPENSE)
            totals['drawings' if drawings else 'expense'] += amount
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_VOUCHER,
                date=datetime.date(year, month, min(row['day'], last_day)), reference=reference,
                narration=self._narration(row, drawings),
                created_by=self.owner,
                lines=[{'account': account, 'debit': amount}, {'account': ChartOfAccount.BANK, 'credit': amount}],
            )
        self.log(f'Expenses {exp["month"]}: Rs {totals["expense"]:,.0f} running costs, '
                 f'Rs {totals["drawings"]:,.0f} owner drawings; staff salary Rs {totals["payroll_skipped"]:,.0f} '
                 'left to payroll.')
        self.result['expenses'] = {k: str(v) for k, v in totals.items()}

    def _narration(self, row, drawings):
        label = self.u.get('expense_labels', {}).get(row['item'])
        text = f"{row['section']}: {row['item']}" + (f' - {label}' if label else '')
        return text + (' (drawings)' if drawings else '')

    def _expense_accounts(self):
        """Equity accounts for drawings lines, one per person: {normalised item: account}."""
        out = {}
        equity = ChartOfAccount.get(ChartOfAccount.OWNER_EQUITY)
        for spec in self.u.get('expense_accounts', []):
            account, _ = ChartOfAccount.objects.get_or_create(
                code=spec['code'],
                defaults={'name': spec['name'], 'account_type': equity.account_type, 'group': equity.group},
            )
            for item in spec['items']:
                out[norm(item)] = account
        return out

    def _reclassify(self, reference, special):
        """Move already-posted lines of a mapped item to its own account (append-only)."""
        moved = 0
        for entry in JournalEntry.objects.filter(reference=reference).prefetch_related('lines__account'):
            item = norm(entry.narration.split(': ', 1)[-1].split(' - ')[0].replace(' (drawings)', '').replace(
                ' (owner drawings)', ''))
            target = special.get(item)
            debit = next((line for line in entry.lines.all() if line.debit), None)
            if target is None or debit is None or debit.account_id == target.id:
                continue
            marker = f'Reclass of entry #{entry.id}'
            if JournalEntry.objects.filter(reference=f'{reference}-RECLASS', narration__startswith=marker).exists():
                continue
            JournalEntry.create_posted(
                source=JournalEntry.SOURCE_VOUCHER, date=entry.date, reference=f'{reference}-RECLASS',
                narration=f'{marker}: {entry.narration} -> {target.name}', created_by=self.owner,
                lines=[{'account': target, 'debit': debit.debit}, {'account': debit.account, 'credit': debit.debit}],
            )
            moved += 1
        if moved:
            self.log(f'Reclassified {moved} expense lines to their own accounts')
