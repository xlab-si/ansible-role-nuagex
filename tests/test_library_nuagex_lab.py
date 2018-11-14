from ansible.compat.tests import unittest

import utils
from library import nuagex_lab

NUAGEX_USERNAME = 'USERNAME'
NUAGEX_PASSWORD = 'PASSWORD'


class TestNuagexLab(utils.AnsibleUnittestingMixin, unittest.TestCase):
    def setUp(self):
        super(self.__class__, self).setUp()
        self.module = nuagex_lab

    def test_module_fail_when_required_args_missing(self):
        with self.assertRaises(utils.AnsibleFailJson):
            utils.set_module_args({})
            self.module.main()


class TestNuagexLabPresent(utils.AnsibleVCRMixin, utils.AnsibleUnittestingMixin, unittest.TestCase):
    def setUp(self):
        super(self.__class__, self).setUp()
        self.module = nuagex_lab
        utils.set_module_args({
            'name': 'integration-tests',
            'state': 'present',
            'nuagex_auth': {
                'username': NUAGEX_USERNAME,
                'password': NUAGEX_PASSWORD
            }
        })
        if not self.is_casette_recording():
            self.prevent_sleeping()

    def test_fresh_lab_created(self):
        with self.assertRaises(utils.AnsibleExitJson) as result:
            self.module.main()
        self.assertTrue(utils.fetch_data(result, 'changed'))

    def test_lab_already_running(self):
        with self.assertRaises(utils.AnsibleExitJson) as result:
            self.module.main()
        self.assertFalse(utils.fetch_data(result, 'changed'))


class TestNuagexLabAbsent(utils.AnsibleVCRMixin, utils.AnsibleUnittestingMixin, unittest.TestCase):
    def setUp(self):
        super(self.__class__, self).setUp()
        self.module = nuagex_lab
        utils.set_module_args({
            'name': 'integration-tests',
            'state': 'absent',
            'nuagex_auth': {
                'username': NUAGEX_USERNAME,
                'password': NUAGEX_PASSWORD
            }
        })
        if not self.is_casette_recording():
            self.prevent_sleeping()

    def test_running_lab_destroyed(self):
        with self.assertRaises(utils.AnsibleExitJson) as result:
            self.module.main()
        self.assertTrue(utils.fetch_data(result, 'changed'))

    def test_lab_already_gone(self):
        with self.assertRaises(utils.AnsibleExitJson) as result:
            self.module.main()
        self.assertFalse(utils.fetch_data(result, 'changed'))

