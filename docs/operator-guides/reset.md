# Resetting Your Data

Resetting your data allows you to drop all previously synced data so that any ensuing sync can start syncing fresh. This is useful if you don't require the data replicated to your destination to be saved permanently or are just testing Airbyte.

Airbyte allows you to reset all streams in the connection, some, or only a single stream (when the connector support per-stream operations).

A sync will automatically start after a completed reset, which commonly backfills all historical data.

## Performing a Reset
To perform a reset, select `Reset your data` in the UI on a connection's status or job history tabs. You will also be prompted to reset affected streams if you edit any stream settings to ensure data continues to sync accurately.

Similarly to a sync job, a reset can be completed as successful, failed, or cancelled. To resolve a failed reset, you should manually drop the tables in the destination so that Airbyte can continue syncing accurately into the destination. 

## Reset behavior
When a reset is successfully completed, all the records are deleted from your destination tables (and files, if using local JSON or local CSV as the destination).

:::info
If you are using destinations that are on the [Destinations v2](/release_notes/upgrading_to_destinations_v2.md) framework, only raw tables will be cleared of their data. Final tables will retain all records from the last sync. 
:::

A reset **DOES NOT** delete any destination tables when using a data warehouse, data lake, database. The schema is retained but will not contain any rows.

:::tip
If you have any orphaned tables or files that are no longer being synced to, they should be cleaned up separately, as Airbyte will not clean them up for you. This can occur when the `Destination Namespace` or `Stream Prefix` connection configuration is changed for an existing connection.
:::
