import os
from distutils.command.build import build

from django.core import management
from setuptools import find_packages, setup

from pretix_roomsharing import __version__


try:
    with open(
        os.path.join(os.path.dirname(__file__), "README.rst"), encoding="utf-8"
    ) as f:
        long_description = f.read()
except Exception:
    long_description = ""


class CustomBuild(build):
    def run(self):
        management.call_command("compilemessages", verbosity=1)
        build.run(self)


cmdclass = {"build": CustomBuild}


setup(
    name="pretix-roomsharing",
    version=__version__,
    description="Pretix roomsharing allows attendees to setup with which people they'd like to share a room",
    long_description=long_description,
    url="https://github.com/Techwolf12/pretix-roomsharing",
    author="Christiaan de Die le Clercq (techwolf12)",
    author_email="contact@techwolf12.nl",
    license="Apache",
    install_requires=[],
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    cmdclass=cmdclass,
    entry_points="""
[pretix.plugin]
pretix_roomsharing=pretix_roomsharing:PretixPluginMeta
""",
)
