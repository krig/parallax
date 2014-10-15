from distutils.core import setup
from parallax import version

long_description = """Parallax SSH provides an interface to executing commands on multiple
nodes at once using SSH. It also provides commands for sending and receiving files to
multiple nodes using SCP."""

setup(name="parallax",
      version=version.VERSION,
      author="Kristoffer Gronlund",
      author_email="krig@koru.se",
      url="https://github.com/krig/parallax/",
      description="Execute commands and copy files over SSH to multiple machines at once",
      long_description=long_description,
      license="BSD",
      platforms=['linux'],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: System Administrators",
          "License :: OSI Approved :: BSD License",
          "Operating System :: POSIX",
          "Programming Language :: Python",
          "Programming Language :: Python :: 2",
          "Programming Language :: Python :: 2.6",
          "Programming Language :: Python :: 2.7",
          "Programming Language :: Python :: 3",
          "Programming Language :: Python :: 3.1",
          "Programming Language :: Python :: 3.2",
          "Topic :: Software Development :: Libraries :: Python Modules",
          "Topic :: System :: Clustering",
          "Topic :: System :: Networking",
          "Topic :: System :: Systems Administration",
      ],
      packages=['parallax'],
      scripts=["bin/parallax-askpass"])
