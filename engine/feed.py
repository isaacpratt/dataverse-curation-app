"""Where the in-app updater finds its feed.

One constant on purpose: config.py (the frozen-layout policy) and
ui/updater.py (the check itself) both need it, and a silent divergence
between the two would point the installer policy at one repo and the
in-app updater at another.
"""

REPO_URL = "https://github.com/isaacpratt/dataverse-curation-app"
