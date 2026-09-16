"""
Seeds realistic demo data for Mumtaz & Co's Sargodha PTC distribution
business, so the POC is usable the moment ``migrate`` finishes: the real
branch structure (Sargodha HQ, Bhalwal, Bhera), the real brand/SKU
catalogue shape seen in their stock sheets, PTC's channel taxonomy
(DD/VDD/WS/VWS/MANDI), the fixed roles from the requirement doc, a demo
login per role, a handful of shops, one purchase order, and a few sales
orders so the dashboard has something to show.

Usage: python manage.py seed_demo_data
Safe to re-run: uses get_or_create throughout.
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from accounting.models import Party
from catalog.models import Brand, Channel, ChannelPrice, SKU
from distribution.models import SalesOrder, SalesOrderLine, SalesTarget, Shop
from hr.models import Employee
from purchasing.models import PurchaseOrder, PurchaseOrderLine
from warehouses.models import SafetyStockLevel, StockLedgerEntry, Warehouse

# Brand / SKU shape lifted from Mumtaz & Co's own stock sheets (CLOSING JAN
# -25.xlsx, ROKAR sheet): brand, variant, pack label, sticks per pack, cost.
BRAND_SKUS = {
    'DUNHILL': [
        ('Swiss', 'SMALL', 10, Decimal('850')),
        ('Lights 20', 'LARGE', 20, Decimal('1450')),
    ],
    'BENSON & HEDGES': [
        ('Lite', '20 HL', 20, Decimal('1400')),
        ('Regular', '20 HL', 20, Decimal('1400')),
    ],
    'GOLD LEAF': [
        ('Classic', 'LEP', 20, Decimal('950')),
        ('Classic', '20 HL', 20, Decimal('1050')),
    ],
    'GOLD LEAF SPECIAL': [
        ('Special', 'LEP 3', 20, Decimal('1000')),
    ],
    'JOHN PLAYER': [
        ('Gold Leaf', '20HL', 20, Decimal('1100')),
    ],
    'CAPSTAN BY PALL MALL': [
        ('Filter', '20HL', 20, Decimal('750')),
        ('International', '125', 20, Decimal('780')),
    ],
    'ROTHMANS': [
        ('International', '20 HL', 20, Decimal('1500')),
    ],
    'VELO': [
        ('PM 6MG', 'CAN', 1, Decimal('450')),
        ('PM 10MG', 'CAN', 1, Decimal('480')),
    ],
    'WILLS': [
        ('Kings', '20 HL', 20, Decimal('1050')),
        ('International', '10 HL', 10, Decimal('550')),
    ],
    'EMBASSY': [
        ('Kings', '20 HL', 20, Decimal('900')),
    ],
    'LUCKY STRIKE': [
        ('Mint', '20 HL', 20, Decimal('1200')),
    ],
}

WAREHOUSES = [
    {'name': 'Sargodha HQ', 'code': 'SGD-HQ', 'location': 'Sargodha', 'is_head_office': True, 'requires_po_approval': False},
    {'name': 'Bhalwal', 'code': 'BHLWAL', 'location': 'Bhalwal, Sargodha', 'is_head_office': False, 'requires_po_approval': True},
    {'name': 'Bhera', 'code': 'BHERA', 'location': 'Bhera, Sargodha', 'is_head_office': False, 'requires_po_approval': True},
]

# Channel type x filer status, with a representative retail/wholesale price uplift.
CHANNEL_DEFS = [
    ('DD - Urban Retail', Channel.TYPE_DD, Channel.NON_FILER),
    ('VDD - Rural Retail', Channel.TYPE_VDD, Channel.NON_FILER),
    ('WS - Urban Wholesale', Channel.TYPE_WS, Channel.NON_FILER),
    ('WS - Urban Wholesale (Filer)', Channel.TYPE_WS, Channel.FILER),
    ('VWS - Rural Wholesale', Channel.TYPE_VWS, Channel.NON_FILER),
    ('MANDI - Wholesale Mandi', Channel.TYPE_MANDI, Channel.NON_FILER),
]

SHOP_NAMES = [
    ('Al-Karam General Store', 'DD - Urban Retail', 'Satellite Town'),
    ('Chowk Bazaar Cigarette Corner', 'DD - Urban Retail', 'Chowk Bazaar'),
    ('Motorway Rest Area Kiosk', 'VDD - Rural Retail', 'M-M2 Motorway'),
    ('Bhalwal Wholesale Traders', 'WS - Urban Wholesale', 'Bhalwal'),
    ('Bhera Mandi Traders', 'MANDI - Wholesale Mandi', 'Bhera Mandi'),
    ('Kot Momin Rural Store', 'VDD - Rural Retail', 'Kot Momin'),
]

DR_NAMES = [
    ('SGD_SGD_DR01', 'Anayat', 'Ali'),
    ('SGD_SGD_DR02', 'Raza', 'Sarwar'),
    ('SGD_SGD_DR03', 'Moavia', 'Khan'),
    ('BHL_BHL_DR01', 'Naeem', 'Sattar'),
    ('BHR_BHR_DR01', 'Tayyab', 'Hussain'),
]


class Command(BaseCommand):
    help = 'Seed demo data: roles, users, brands/SKUs, channels/pricing, warehouses, shops, sample transactions.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding roles & users...')
        groups = self._seed_roles()
        users = self._seed_users(groups)

        self.stdout.write('Seeding warehouses...')
        warehouses = self._seed_warehouses()

        self.stdout.write('Seeding brands & SKUs...')
        skus = self._seed_catalog(users['owner'])

        self.stdout.write('Seeding channels & pricing...')
        channels = self._seed_channels(skus, users['owner'])

        self.stdout.write('Seeding shops...')
        shops = self._seed_shops(channels)

        self.stdout.write('Seeding DRs, employees & targets...')
        self._seed_drs_and_employees(users, groups, warehouses, channels)

        self.stdout.write('Seeding opening stock & safety levels...')
        self._seed_opening_stock(warehouses, skus, users['owner'])

        self.stdout.write('Seeding a sample purchase order...')
        self._seed_purchase_order(warehouses, skus, users['owner'])

        self.stdout.write('Seeding sample sales orders (last 14 days)...')
        self._seed_sales_orders(warehouses, skus, channels, shops, users)

        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))
        self.stdout.write('Demo logins (all passwords: "demopass123"):')
        for role, username in [
            ('Owner', 'owner'), ('Distribution Manager', 'dm_sargodha'),
            ('FSO', 'fso_sargodha'), ('Sales Manager', 'salesmgr_sargodha'),
            ('Warehouse Staff', 'warehouse_sargodha'), ('DR', 'dr_anayat'),
        ]:
            self.stdout.write(f'  {role:<22} username={username}')

    # -- Roles & users -----------------------------------------------------

    def _seed_roles(self):
        call_command('seed_roles')
        return {role_name: Group.objects.get(name=role_name) for role_name in settings.ALL_ROLES}

    def _seed_users(self, groups):
        def make_user(username, first, last, role_name, is_superuser=False, warehouse=None):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'email': f'{username}@mumtazco.example'},
            )
            if created:
                user.set_password('demopass123')
                # Only the Owner gets Django admin / user-management access
                # (accounts.views.UserViewSet requires IsAdminUser == is_staff);
                # every other role authenticates via the API/JWT only.
                user.is_staff = is_superuser
                user.is_superuser = is_superuser
                user.save()
            user.groups.add(groups[role_name])
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if warehouse:
                profile.warehouse = warehouse
                profile.save()
            return user

        sargodha = Warehouse.objects.filter(code='SGD-HQ').first()

        owner = make_user('owner', 'Mumtaz', 'Owner', settings.ROLE_OWNER, is_superuser=True)
        dm = make_user('dm_sargodha', 'Distribution', 'Manager', settings.ROLE_DISTRIBUTION_MANAGER)
        fso = make_user('fso_sargodha', 'Field', 'Officer', settings.ROLE_FSO, warehouse=sargodha)
        sales_mgr = make_user('salesmgr_sargodha', 'Sales', 'Manager', settings.ROLE_SALES_MANAGER, warehouse=sargodha)
        wh_staff = make_user('warehouse_sargodha', 'Warehouse', 'Staff', settings.ROLE_WAREHOUSE_STAFF, warehouse=sargodha)

        return {'owner': owner, 'dm': dm, 'fso': fso, 'sales_mgr': sales_mgr, 'warehouse_staff': wh_staff}

    # -- Warehouses ----------------------------------------------------------

    def _seed_warehouses(self):
        warehouses = {}
        for wh in WAREHOUSES:
            obj, _ = Warehouse.objects.get_or_create(code=wh['code'], defaults=wh)
            warehouses[wh['code']] = obj
        return warehouses

    # -- Catalog ---------------------------------------------------------------

    def _seed_catalog(self, owner):
        skus = []
        for brand_index, (brand_name, variants) in enumerate(BRAND_SKUS.items(), start=1):
            brand, _ = Brand.objects.get_or_create(
                name=brand_name, defaults={'code': f'{brand_name[:3].upper()}{brand_index:02d}'}
            )
            for variant, pack_size, sticks, cost in variants:
                variant_slug = ''.join(ch for ch in variant if ch.isalnum())[:3].upper()
                pack_slug = ''.join(ch for ch in pack_size if ch.isalnum()).upper()
                code = f'{brand.code}-{variant_slug}{pack_slug}'
                sku, created = SKU.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': f'{brand_name} {variant} {pack_size}',
                        'brand': brand, 'variant': variant, 'pack_size': pack_size,
                        'sticks_per_pack': sticks, 'current_cost_price': cost,
                    },
                )
                if created:
                    sku.set_cost_price(cost, changed_by=owner, note='Initial seed')
                skus.append(sku)
        return skus

    # -- Channels & pricing ----------------------------------------------------

    def _seed_channels(self, skus, owner):
        channels = {}
        for name, ctype, filer in CHANNEL_DEFS:
            channel, _ = Channel.objects.get_or_create(
                name=name, channel_type=ctype, filer_status=filer,
                defaults={'opened_on': date(2026, 1, 1)},
            )
            channels[name] = channel
            for sku in skus:
                # Retail channels sell close to cost + a fixed margin; wholesale/mandi trims the margin.
                margin = Decimal('1.15') if ctype in (Channel.TYPE_DD, Channel.TYPE_VDD) else Decimal('1.06')
                price = (sku.current_cost_price * margin).quantize(Decimal('1'))
                ChannelPrice.objects.get_or_create(
                    channel=channel, sku=sku, effective_from=date(2026, 1, 1),
                    defaults={'price': price, 'changed_by': owner},
                )
        return channels

    # -- Shops -------------------------------------------------------------

    def _seed_shops(self, channels):
        shops = []
        for name, channel_name, locality in SHOP_NAMES:
            shop, _ = Shop.objects.get_or_create(
                name=name,
                defaults={
                    'channel': channels[channel_name], 'locality': locality,
                    'credit_limit': Decimal('50000') if 'Wholesale' in channel_name or 'Mandi' in channel_name else Decimal('0'),
                },
            )
            shops.append(shop)
        return shops

    # -- DRs, employees, targets -----------------------------------------------

    def _seed_drs_and_employees(self, users, groups, warehouses, channels):
        wh_by_prefix = {'SGD': warehouses['SGD-HQ'], 'BHL': warehouses['BHLWAL'], 'BHR': warehouses['BHERA']}
        dr_users = []
        for i, (dr_code, first, last) in enumerate(DR_NAMES, start=1):
            username = f'dr_{first.lower()}'
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'email': f'{username}@mumtazco.example'},
            )
            if created:
                user.set_password('demopass123')
                user.save()
            user.groups.add(groups[settings.ROLE_DR])
            prefix = dr_code.split('_')[0]
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.dr_code = dr_code
            profile.warehouse = wh_by_prefix.get(prefix, warehouses['SGD-HQ'])
            profile.supervisor = users['fso'].profile
            profile.save()
            dr_users.append(user)

            Employee.objects.get_or_create(
                employee_number=f'EMP-{100 + i}',
                defaults={
                    'full_name': f'{first} {last}', 'cnic': f'38403-{1000000 + i}-1',
                    'role': 'Distribution Representative', 'warehouse': profile.warehouse,
                    'user': user, 'monthly_salary': Decimal('35000'), 'commission_rate': Decimal('2.5'),
                    'hire_date': date(2024, 1, 1),
                },
            )

            SalesTarget.objects.get_or_create(
                dr=user, channel=channels['DD - Urban Retail'], year=2026, month=9,
                defaults={'target_volume_m': Decimal('120.0')},
            )

        # A couple of non-DR staff on the books too, for HR to have more than one role.
        Employee.objects.get_or_create(
            employee_number='EMP-001', defaults={
                'full_name': 'Mumtaz Owner', 'cnic': '38403-0000001-1', 'role': 'Owner',
                'warehouse': warehouses['SGD-HQ'], 'user': users['owner'],
                'monthly_salary': Decimal('0'), 'hire_date': date(2015, 1, 1),
            },
        )
        Employee.objects.get_or_create(
            employee_number='EMP-002', defaults={
                'full_name': 'Distribution Manager', 'cnic': '38403-0000002-1', 'role': 'Distribution Manager',
                'warehouse': warehouses['SGD-HQ'], 'user': users['dm'],
                'monthly_salary': Decimal('80000'), 'hire_date': date(2018, 3, 1),
            },
        )
        return dr_users

    # -- Opening stock & safety levels ------------------------------------------

    def _seed_opening_stock(self, warehouses, skus, owner):
        for wh in warehouses.values():
            for sku in skus:
                qty = Decimal(random.randint(800, 2500))
                StockLedgerEntry.objects.create(
                    warehouse=wh, sku=sku, entry_type=StockLedgerEntry.OPENING_BALANCE,
                    quantity_change=qty, reference='SEED-OPENING', created_by=owner,
                )
                SafetyStockLevel.objects.get_or_create(
                    warehouse=wh, sku=sku, defaults={'minimum_quantity': Decimal('300')}
                )

    # -- Sample purchase order --------------------------------------------------

    def _seed_purchase_order(self, warehouses, skus, owner):
        ptc, _ = Party.objects.get_or_create(
            name='Pakistan Tobacco Company (PTC)',
            defaults={'party_type': Party.SUPPLIER, 'address': 'PTC Head Office'},
        )
        po, created = PurchaseOrder.objects.get_or_create(
            po_number='PO-2026-00001',
            defaults={
                'ptc_reference_number': 'PTC-SAP-778812',
                'warehouse': warehouses['SGD-HQ'], 'supplier': ptc,
                'order_date': date(2026, 9, 1), 'created_by': owner,
            },
        )
        if created:
            for sku in skus[:5]:
                PurchaseOrderLine.objects.create(
                    purchase_order=po, sku=sku, quantity=Decimal('100'), unit_cost=sku.current_cost_price
                )
            po.submit()

    # -- Sample sales orders -----------------------------------------------------

    def _seed_sales_orders(self, warehouses, skus, channels, shops, users):
        dr_users = list(User.objects.filter(groups__name=settings.ROLE_DR))
        if not dr_users:
            return
        so_counter = 1
        today = timezone.localdate()
        for days_ago in range(14, -1, -1):
            order_date = today - timedelta(days=days_ago)
            for _ in range(random.randint(2, 5)):
                shop = random.choice(shops)
                dr = random.choice(dr_users)
                sku_choices = random.sample(skus, k=min(3, len(skus)))
                so_number = f'SO-2026-{so_counter:05d}'
                so_counter += 1
                so, created = SalesOrder.objects.get_or_create(
                    so_number=so_number,
                    defaults={
                        'ptc_reference_number': f'PTC-SALE-{so_counter:06d}',
                        'shop': shop, 'channel': shop.channel, 'warehouse': warehouses['SGD-HQ'],
                        'dr': dr, 'order_date': order_date,
                        'timestamp': timezone.make_aware(
                            datetime.combine(order_date, datetime.min.time()) + timedelta(hours=10)
                        ),
                        'created_by': dr,
                    },
                )
                if not created:
                    continue
                for sku in sku_choices:
                    price = ChannelPrice.current_price(shop.channel_id, sku.id, order_date) or sku.current_cost_price
                    SalesOrderLine.objects.create(
                        sales_order=so, sku=sku, quantity=Decimal(random.randint(2, 15)), unit_price=price,
                    )
                try:
                    so.confirm(user=dr)
                except ValueError:
                    pass
