# Parallax SSH

Parallax SSH is a fork of [Parallel SSH][pssh] which focuses less on
command-line tools and more on providing a flexible and programmable
API that can be used by Python application developers to perform SSH
operations across multiple machines.

## Installation

Parallax intends to be compatible with Python 2.6 and above (including
Python 3.1 and greater), but is primarily tested with Python 2.7.

Installation requires setuptools or ez_setup.py. The latter can be
downloaded [here][ez].

Once those requirements are fulfilled, installation is as simple as:

    # sudo python setup.py install

Packaged versions of Parallax SSH for various distributions can be
downloaded from the openSUSE [OBS][obs].

To install via PyPI, use `pip`:

    # pip install parallax

Share and enjoy!

## Usage

* `parallax.call(hosts, cmdline, opts)`

  Executes the given command on a set of hosts, collecting the output.

  Returns a dict mapping the hostname of
  each host either to a tuple containing a return code,
  stdout and stderr, or an `parallax.Error` instance
  describing the error.

* `parallax.copy(hosts, src, dst, opts)`

  Copies files from `src` on the local machine to `dst` on the
  remote hosts.

  Returns a dict mapping the hostname of
  each host either to a path, or an `parallax.Error` instance
  describing the error.

* `parallax.slurp(hosts, src, dst, opts)`

  Copies files from `src` on the remote hosts to a local folder for
  each of the remote hosts.

  Returns a dict mapping the hostname of
  each host either to a path, or an `parallax.Error` instance
  describing the error.

## How it works

By default, Parallax SSH uses at most 32 SSH process in parallel to
SSH to the nodes. By default, it uses a timeout of one minute to SSH
to a node and obtain a result.

## Environment variables

* `PARALLAX_HOSTS`
* `PARALLAX_USER`
* `PARALLAX_PAR`
* `PARALLAX_OUTDIR`
* `PARALLAX_VERBOSE`
* `PARALLAX_OPTIONS`


  [pssh]: https://code.google.com/p/parallel-ssh/ "parallel-ssh"
  [ez]: http://peak.telecommunity.com/dist/ez_setup.py "ez_setup.py"
  [obs]: https://build.opensuse.org/package/show/devel:languages:python/python-parallax "OBS:python-parallax"
