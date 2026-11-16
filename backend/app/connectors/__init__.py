"""Clinic-level connectors for the Integration Hub (Admin → Integrations).

Each connector is one entry in ``registry.CONNECTORS`` (name, category, how it signs in, its settings, what it syncs)
plus an adapter class with ``test``, ``push`` and ``remove``. Changing or adding a provider never touches booking,
payment or permission code: the hub, the sync queue (``sync.py``) and the hooks call the adapter.
"""
