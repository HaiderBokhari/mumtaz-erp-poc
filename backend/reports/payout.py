"""
DR monthly payout: the pay grade's fixed components plus commission per M
sold (retail vs scattered rates per SKU), from the distributor's revised
salary structure and brand-wise commission sheet. Commission is computed on
the *actual* book — what the DR physically sold — not BIZOM.

Attendance isn't captured yet (biometric import is a later phase), so the
attendance allowance is assumed earned in full; the target bonus is paid
when actual volume meets the month's SalesTarget.
"""
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User

from distribution.models import ActualSale, SalesTarget

D0 = Decimal('0')


def dr_payout_rows(year, month):
    sales = (
        ActualSale.objects.filter(date__year=year, date__month=month)
        .select_related('sku__commission_rate')
    )
    per_dr = defaultdict(lambda: {'retail_m': D0, 'scattered_m': D0, 'commission': D0, 'value': D0, 'sources': set()})
    for sale in sales:
        row = per_dr[sale.dr_id]
        rate = getattr(sale.sku, 'commission_rate', None)
        if sale.bucket == ActualSale.BUCKET_SCATTERED:
            row['scattered_m'] += sale.quantity_m
            per_m = rate.scattered_per_m if rate else D0
        else:
            row['retail_m'] += sale.quantity_m
            per_m = rate.retail_per_m if rate else D0
        row['commission'] += sale.quantity_m * per_m
        row['value'] += sale.quantity_m * sale.unit_price
        row['sources'].add(sale.source)

    targets = defaultdict(lambda: D0)
    for t in SalesTarget.objects.filter(year=year, month=month):
        targets[t.dr_id] += t.target_volume_m

    rows = []
    drs = (
        User.objects.filter(groups__name=settings.ROLE_DR)
        .select_related('profile', 'employee_record__pay_grade')
        .order_by('profile__dr_code')
    )
    for user in drs:
        stats = per_dr.get(user.id)
        employee = getattr(user, 'employee_record', None)
        grade = employee.pay_grade if employee else None
        actual_m = (stats['retail_m'] + stats['scattered_m']) if stats else D0
        target_m = targets.get(user.id, D0)
        achieved = bool(target_m) and actual_m >= target_m
        fixed = grade.fixed if grade else D0
        attendance = grade.attendance_allowance if grade else D0
        target_bonus = grade.target_bonus if (grade and achieved) else D0
        vr = grade.vr_allowance if grade else D0
        rtm = grade.rtm_allowance if grade else D0
        salary_total = fixed + attendance + target_bonus + vr + rtm
        commission = (stats['commission'] if stats else D0).quantize(Decimal('0.01'))
        rows.append({
            'dr_id': user.id,
            'employee_id': employee.id if employee else None,
            'dr_code': user.profile.dr_code,
            'name': user.get_full_name() or user.username,
            'grade': grade.name if grade else '',
            'retail_m': (stats['retail_m'] if stats else D0).quantize(Decimal('0.001')),
            'scattered_m': (stats['scattered_m'] if stats else D0).quantize(Decimal('0.001')),
            'actual_m': actual_m.quantize(Decimal('0.001')),
            'actual_value': (stats['value'] if stats else D0).quantize(Decimal('0.01')),
            'target_m': target_m,
            'achievement_pct': (actual_m / target_m * 100).quantize(Decimal('0.1')) if target_m else None,
            'target_achieved': achieved,
            'fixed': fixed, 'attendance': attendance, 'target_bonus': target_bonus,
            'vr_allowance': vr, 'rtm_allowance': rtm,
            'salary_total': salary_total,
            'commission': commission,
            'total_payable': salary_total + commission,
            'assumed': bool(stats) and ActualSale.SOURCE_BIZOM_ASSUMED in stats['sources'],
        })
    return rows
