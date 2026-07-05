# State Registry Access Inventory

This document tracks the official public entry points for U.S. state sex offender registries and a conservative recommendation for how to obtain data lawfully.

Source basis:

- Official state registry links were taken from the DOJ Dru Sjodin National Sex Offender Public Website registry directory on 2026-07-04.
- This inventory records public entry points only. It does not imply that bulk collection, scraping, or automation is authorized.

## Method categories

- `official_public_registry_ui`: an official state or agency search portal appears to be the public access point.
- `vendor_hosted_public_registry_ui`: a state points to a vendor-hosted registry UI such as `communitynotification.com`, `icrimewatch.net`, or `sheriffalerts.com`.
- `official_landing_page`: the state link appears to be a program or informational landing page that likely routes users to search tools or policies.
- `multiple_official_entry_points`: the state publishes more than one official public registry/search entry point.

## Recommended acquisition order

1. Use an official API, bulk export, or machine-readable feed only if the jurisdiction explicitly documents and permits it.
2. If no such feed is published, contact the state agency for a data-sharing path, records request process, or written automation permission.
3. Treat the public registry website as a manual or low-volume verification surface unless terms clearly allow more.
4. Before any connector is implemented, review `robots.txt`, terms of use, rate limits, and any state-specific legal restrictions.

## Data file

The detailed state-by-state inventory is in [data/reference/state_registry_access.csv](/home/carnufex/registry-platform/data/reference/state_registry_access.csv).

## Notes

- Minnesota is listed with two official entry points because the DOJ directory publishes both a Bureau of Criminal Apprehension search portal and a Department of Corrections public registrant search.
- District of Columbia is included in the CSV for operational completeness, but the 50-state list remains separated from territories and tribes.
- For the current platform, assume nullable or inconsistent fields across all jurisdictions unless the source proves otherwise.
