import gzip
import json

from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from distribution.models import ActualSale, DRSettlement, SalesOrder, Shop

from .client_bundle import BundleLoader


class ClientBundleUploadView(APIView):
    """
    Owner-only: load a bundle built by ``build_client_bundle`` into this
    deployment. Real client data never goes through git (the repo is
    public), so this is how a hosted instance gets it. Resets business data.
    """
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'Expected a multipart "file" field with bundle.json.gz.'}, status=400)
        try:
            bundle = json.loads(gzip.decompress(upload.read()).decode('utf-8'))
        except (OSError, ValueError) as exc:
            return Response({'detail': f'Not a valid bundle: {exc}'}, status=400)
        log = []
        BundleLoader(bundle, log=log.append).run()
        return Response({
            'log': log, 'shops': Shop.objects.count(), 'bizom_orders': SalesOrder.objects.count(),
            'actual_sale_rows': ActualSale.objects.count(), 'settlements': DRSettlement.objects.count(),
        })
