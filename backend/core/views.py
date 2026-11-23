import gzip
import json
import threading
import traceback
from pathlib import Path

from django.db import connection
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from distribution.models import ActualSale, DRSettlement, SalesOrder, Shop

from .client_bundle import BundleLoader
from .client_updates import UpdateApplier

# Shared by all gunicorn workers in the container, so any worker can report progress.
STATUS_FILE = Path('/tmp/client_bundle_status.json')


def _write_status(**status):
    STATUS_FILE.write_text(json.dumps(status))


def _load_in_background(bundle):
    log = []

    def step(message):
        log.append(message)
        _write_status(state='running', log=log)

    try:
        if bundle.get('kind') == 'updates':
            result = UpdateApplier(bundle, log=step).run()
            _write_status(state='done', log=log, result=result)
            return
        BundleLoader(bundle, log=step).run()
        _write_status(
            state='done', log=log, shops=Shop.objects.count(), bizom_orders=SalesOrder.objects.count(),
            actual_sale_rows=ActualSale.objects.count(), settlements=DRSettlement.objects.count(),
        )
    except Exception:  # noqa: BLE001 - surface any failure to the uploader
        _write_status(state='failed', log=log, error=traceback.format_exc()[-3000:])
    finally:
        connection.close()


class ClientBundleUploadView(APIView):
    """
    Owner-only: load a bundle built by ``build_client_bundle`` into this
    deployment. Real client data never goes through git (the repo is
    public), so this is how a hosted instance gets it. A full bundle resets
    business data; an updates file (``build_client_updates``) only adds to it.

    POST starts the load in the background (small hosts take minutes, longer
    than a request may run); GET reports progress.
    """
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser]

    def get(self, request):
        if not STATUS_FILE.exists():
            return Response({'state': 'idle'})
        return Response(json.loads(STATUS_FILE.read_text()))

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'Expected a multipart "file" field with bundle.json.gz.'}, status=400)
        if STATUS_FILE.exists() and json.loads(STATUS_FILE.read_text()).get('state') == 'running':
            return Response({'detail': 'A load is already running.'}, status=409)
        try:
            bundle = json.loads(gzip.decompress(upload.read()).decode('utf-8'))
        except (OSError, ValueError) as exc:
            return Response({'detail': f'Not a valid bundle: {exc}'}, status=400)
        _write_status(state='running', log=['Upload received, loading...'])
        threading.Thread(target=_load_in_background, args=(bundle,), daemon=True).start()
        return Response({'state': 'running'}, status=202)
