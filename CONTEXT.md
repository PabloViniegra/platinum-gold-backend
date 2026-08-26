# Dataset Ingestion Context

This context defines the language used for the catalog dataset and its offline
publication flow.

## Language

**Upstream source**:
The external authority from which catalog information is ultimately obtained.
For this project, Platinum God is the upstream source.
_Avoid_: runtime source, API source

**Snapshot**:
A complete, versioned set of catalog records prepared for one publication
attempt.
_Avoid_: dump, seed file

**Dataset version**:
The identity assigned to a snapshot by the upstream publication that produced
it.
_Avoid_: sync version, ingestion timestamp

**Ingestion**:
The controlled publication of a validated snapshot into the catalog.
_Avoid_: scraping, import job

**Last sync**:
The UTC time at which the most recent ingestion was successfully committed.
_Avoid_: fetch time, scrape time

**Upsert-only update**:
An update policy that inserts new records and updates matching records while
preserving records absent from the incoming snapshot.
_Avoid_: full replacement, reconciliation
