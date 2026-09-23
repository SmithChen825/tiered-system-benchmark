# Task L2-03: Repair saved-note import and export

The notes service starts and its health endpoint works, but saved notes are not reliably loaded, exported, or preserved after importing a backup and restarting the service. Restore the existing JSON import/export workflow while preserving the supplied note schema, endpoints, seed notes, single-service FastAPI architecture, and persistent storage volume. Invalid backups must still be rejected without replacing the saved notes.

