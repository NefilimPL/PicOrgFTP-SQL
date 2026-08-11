# Backup path security design

## Goal

Block path traversal in the SQLite backup comparison and restore APIs without preventing an administrator from retaining backups in a deliberately registered archive directory.

## Design

`sqlite_backup` will resolve a selected backup path before using it.  The resolved target must be an existing regular `.sqlite` file below one of the trusted backup roots.  Resolving both target and roots rejects `..` segments and symbolic links that escape a root.

The default `BACKUP` directory remains trusted.  Backup settings gain `archive_dirs`: normalized, unique absolute directory paths.  An administrator can enter these paths in the web settings, and history lookup reads the default directory plus registered archive directories.  Newly created backups and retention continue to use only the default `BACKUP` directory.

The web API converts invalid selections to HTTP 400.  The browser continues to send the selected history path; server-side validation is the authority.

## Compatibility and accessibility

Redundant `min-height: auto` declarations will be removed.  The Safari user-selection prefix will be included and the unsupported drag declaration removed.  The thumbnail checkbox will receive an explicit HTML label.
