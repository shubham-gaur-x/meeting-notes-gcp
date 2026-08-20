"""Ingestion connectors — one per upstream source.

These replace Airbyte entirely (CLAUDE.md). Each source fetches what changed
since a watermark and stages it; nothing here interprets content, which is
the pipeline's job in Phase 6.
"""
