"""The clinic's own S3-compatible bucket (see app/services/clinic_storage.py for routing and moving files)."""
from __future__ import annotations

from app.connectors.base import Adapter
from app.integrations.http import IntegrationAPIError


class ClinicBucket(Adapter):
    def test(self) -> str:
        from app.services.clinic_storage import client_for
        from app.services.platform_tests import test_bucket

        cfg = self.ctx.config
        ok, message = test_bucket(cfg.get("s3_bucket") or "", cfg.get("s3_prefix") or "", client=client_for(cfg, self.ctx.secrets()))
        if not ok:
            raise IntegrationAPIError(message)
        return message
