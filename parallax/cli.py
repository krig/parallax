# Copyright (c) 2009-2012, Andrew McNabb
# Copyright (c) 2003-2008, Brent N. Chun

import optparse
import os
import shlex
import sys
import textwrap

from parallax import version

DEFAULT_PARALLELISM = 32
DEFAULT_TIMEOUT     = 0 # "infinity" by default
