#!/bin/sh
# The real CLI binary is installed as /usr/bin/zed.real; this wrapper
# disables Zed's own auto-updater (it reads ZED_UPDATE_EXPLANATION at
# startup and skips update checks/installs when it is set) so updates
# only happen through xbps, not by Zed silently replacing its own files.
export ZED_UPDATE_EXPLANATION='Updates are handled by your package manager (xbps-install -u zed)'
exec /usr/bin/zed.real "$@"
