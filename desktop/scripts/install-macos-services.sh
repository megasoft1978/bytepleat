#!/bin/sh
set -eu
usage() { echo "Usage: $0 --service-app BUILT.app --bytepleat-app Bytepleat.app" >&2; exit 2; }
[ "$#" -eq 4 ] && [ "$1" = "--service-app" ] && [ "$3" = "--bytepleat-app" ] || usage
service_app=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
bytepleat_app=$(cd "$(dirname "$4")" && pwd)/$(basename "$4")
[ -x "$service_app/Contents/MacOS/BytepleatServices" ] || { echo "Invalid service app: $service_app" >&2; exit 1; }
[ -x "$bytepleat_app/Contents/MacOS/bytepleat-desktop" ] || { echo "Invalid Bytepleat app: $bytepleat_app" >&2; exit 1; }
destination="$HOME/Library/Services/BytepleatServices.app"
mkdir -p "$HOME/Library/Services"
if [ -e "$destination" ]; then echo "Refusing to replace existing path: $destination" >&2; exit 1; fi
ditto "$service_app" "$destination"
/usr/libexec/PlistBuddy -c "Set :BytepleatApplicationPath $bytepleat_app" "$destination/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :BytepleatInstallerOwner string io.github.megasoft1978.bytepleat.desktop.services" "$destination/Contents/Info.plist"
# Changing the configured application path modifies the bundle: re-sign this
# local development copy ad hoc. Public distribution needs Developer ID signing.
codesign --force --sign - "$destination"
open -a "$destination"
echo "Installed and registered per user at: $destination"
