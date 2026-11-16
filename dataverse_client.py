"""Dataverse Native API client - compatibility shim.

The implementation moved to the ``client`` package (dv-hcg.21):

- ``client.constants`` / ``client.errors`` / ``client.http`` / ``client.parsers``
  / ``client.caches`` / ``client.client``

Importing ``dataverse_client`` keeps working for every existing import site
(``from dataverse_client import ...`` and ``import dataverse_client`` alike);
new code should import from ``client`` directly.
"""

from client import *  # noqa: F403 - intentional compatibility re-export
