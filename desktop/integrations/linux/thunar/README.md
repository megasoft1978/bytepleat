# Thunar custom actions (manual, per user)

The Linux installer adds a launcher, KDE service menu, and Nautilus extension. Thunar
custom actions are configured in Thunar because its XML action registry is managed
by the desktop environment and may be shared with user choices.

1. Open **Edit → Configure custom actions → Add**.
2. Set the name to **Compress with Bytepleat** and the command to:

   `"/absolute/path/to/bytepleat-desktop" --create -- %F`

3. Add a second action named **Extract with Bytepleat**, with command:

   `"/absolute/path/to/bytepleat-desktop" --extract -- %F`

4. In **Appearance Conditions**, choose files and directories as appropriate.

Replace `/absolute/path/to/bytepleat-desktop` with the executable path supplied to
the installer (quote it if it contains spaces). Thunar substitutes `%F` with
separate selected local paths; each substituted filename remains its own argument.
The desktop application receives the shared
`--create -- PATH...` or `--extract -- PATH...` contract. These actions are optional
and can be removed in the same dialog.
