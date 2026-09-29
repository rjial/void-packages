#!/bin/sh
export CHROME_VERSION_EXTRA="void-xbps"
CHROME_WRAPPER="$(readlink -f "$0")"
export CHROME_WRAPPER
export LD_LIBRARY_PATH="/opt/helium:${LD_LIBRARY_PATH}"
exec /opt/helium/helium "$@"
