#!/usr/bin/python

# Copyright (c) 2013, Kristoffer Gronlund

import os
import sys
import unittest
import tempfile
import shutil

basedir, bin = os.path.split(os.path.dirname(os.path.abspath(sys.argv[0])))
sys.path.insert(0, "%s" % basedir)

print basedir

from psshlib import api as pssh

if os.getenv("TEST_HOSTS") is None:
    raise Exception("Must define TEST_HOSTS")
g_hosts = os.getenv("TEST_HOSTS").split()

if os.getenv("TEST_USER") is None:
    raise Exception("Must define TEST_USER")
g_user = os.getenv("TEST_USER")

class CallTest(unittest.TestCase):
    def testSimpleCall(self):
        opts = pssh.Options()
        opts.default_user = g_user
        for host, result in pssh.call(g_hosts, "ls -l /", opts).iteritems():
            rc, out, err = result
            self.assertEqual(rc, 0)
            self.assert_(len(out) > 0)

    def testUptime(self):
        opts = pssh.Options()
        opts.default_user = g_user
        for host, result in pssh.call(g_hosts, "uptime", opts).iteritems():
            rc, out, err = result
            self.assertEqual(rc, 0)
            self.assert_(out.find("load average") != -1)

    def testFailingCall(self):
        opts = pssh.Options()
        opts.default_user = g_user
        for host, result in pssh.call(g_hosts, "touch /foofoo/barbar/jfikjfdj", opts).iteritems():
            self.assert_(isinstance(result, pssh.Error))
            self.assert_(str(result).find('with error code') != -1)

class CopySlurpTest(unittest.TestCase):
    def setUp(self):
        self.tmpDir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpDir)

    def testCopyFile(self):
        opts = pssh.Options()
        opts.default_user = g_user
        opts.localdir = self.tmpDir
        by_host = pssh.copy(g_hosts, "/etc/hosts", "/tmp/pssh.test", opts)
        for host, result in by_host.iteritems():
            rc, _, _ = result
            self.assertEqual(rc, 0)

        by_host = pssh.slurp(g_hosts, "/tmp/pssh.test", "pssh.test", opts)
        for host, result in by_host.iteritems():
            rc, _, _, path = result
            self.assertEqual(rc, 0)
            self.assert_(path.endswith('%s/pssh.test' % (host)))

if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(CallTest, "test"))
    suite.addTest(unittest.makeSuite(CopySlurpTest, "test"))
    unittest.TextTestRunner().run(suite)
