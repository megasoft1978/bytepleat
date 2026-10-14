#!/bin/sh
set -eu
destination="$HOME/Library/Services/BytepleatServices.app"
if [ ! -e "$destination" ]; then echo "No installed Bytepleat Services integration"; exit 0; fi
[ ! -L "$destination" ] || { echo "Refusing to remove a symbolic link" >&2; exit 1; }
owner=$(/usr/libexec/PlistBuddy -c 'Print :BytepleatInstallerOwner' "$destination/Contents/Info.plist" 2>/dev/null || true)
[ "$owner" = io.github.megasoft1978.bytepleat.desktop.services ] || { echo "Refusing to remove a bundle not installed by Bytepleat" >&2; exit 1; }
# Preserve a recoverable copy for uninstall; never delete an unknown bundle.
backup_root="$HOME/Library/Application Support/Bytepleat/UninstalledServices"
mkdir -p "$backup_root"
backup=$(mktemp -d "$backup_root/BytepleatServices.XXXXXX")
mv "$destination" "$backup/BytepleatServices.app"
echo "Disabled Bytepleat Services; recoverable bundle retained at $backup"
