"""
src/delivery/file_sync.py
--------------------------
Copies completed PDF resumes to a local sync directory.

This module provides a simple file-copy integration point for local cloud sync
clients (e.g., Google Drive desktop app, Dropbox, iCloud Drive) by writing
output to a configurable directory that the sync client monitors.

The sync directory is read from the FILE_SYNC_DIR environment variable.
If FILE_SYNC_DIR is not set, this step is skipped silently.

Directory structure within FILE_SYNC_DIR:
    {FILE_SYNC_DIR}/
        ai_engineering/
            {company}_{role}_{date}.pdf
        data_science/
            {company}_{role}_{date}.pdf
"""

