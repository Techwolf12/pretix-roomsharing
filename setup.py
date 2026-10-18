import os

from setuptools import setup

# pretix-plugin-build runs compilemessages, which imports DJANGO_SETTINGS_MODULE if it
# is set. In the pretix Docker image that is "production_settings", which can't be
# imported in pip's build environment, so building from source would fail.
os.environ.pop("DJANGO_SETTINGS_MODULE", None)

setup()
