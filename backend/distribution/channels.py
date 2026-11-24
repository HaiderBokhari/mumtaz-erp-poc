"""
Sales channel of an actual sale (team request 24 Nov 2026: separate
channel-wise sales for DD, VDD, UWS, RWS, MANDI and shop sale).

A DR's own channel lives on ``UserProfile.sales_channel``: DD for urban
routes, VDD for rural, MANDI for the wholesale mandi device and SHOP for the
shop-sale device (RTFs book their sales there). What a DD/VDD DR sells in
scattered wholesale counts as UWS/RWS. Codes follow ``Channel.channel_type``
(WS = UWS, VWS = RWS); SHOP has no BIZOM price list of its own and is
priced like DD.
"""
from catalog.models import Channel

SHOP = 'SHOP'
ORDER = [Channel.TYPE_DD, Channel.TYPE_VDD, Channel.TYPE_WS, Channel.TYPE_VWS, Channel.TYPE_MANDI, SHOP]
LABELS = {
    Channel.TYPE_DD: 'DD', Channel.TYPE_VDD: 'VDD', Channel.TYPE_WS: 'UWS', Channel.TYPE_VWS: 'RWS',
    Channel.TYPE_MANDI: 'Mandi', SHOP: 'Shop sale',
}
SCATTERED = {Channel.TYPE_DD: Channel.TYPE_WS, Channel.TYPE_VDD: Channel.TYPE_VWS}


def dr_channel(user):
    return getattr(getattr(user, 'profile', None), 'sales_channel', '') or Channel.TYPE_DD


def sale_channel(dr_ch, bucket):
    if bucket == 'SCATTERED':
        return SCATTERED.get(dr_ch, dr_ch)
    return dr_ch


def price_channel_type(channel_type):
    return Channel.TYPE_DD if channel_type == SHOP else channel_type


def backfill_sale_channels():
    """Tag actual-sale rows that have no channel yet from their DR and bucket."""
    from django.contrib.auth.models import User

    from .models import ActualSale

    n = 0
    for user in User.objects.filter(actual_sales__channel_type='').distinct().select_related('profile'):
        ch = dr_channel(user)
        for bucket in ('RETAIL', 'SCATTERED'):
            n += ActualSale.objects.filter(dr=user, bucket=bucket, channel_type='').update(
                channel_type=sale_channel(ch, bucket))
    return n
