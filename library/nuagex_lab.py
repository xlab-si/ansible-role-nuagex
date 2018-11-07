#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: nuagex

short_description: Ensure a running nuagex sandbox

version_added: "2.7"

description:
    - "This is my longer description explaining my sample module"

options:
    name:
        description:
            - This is the message to send to the sample module
        required: true
    new:
        description:
            - Control to demo if the result of this module is changed or not
        required: false

author:
    - Miha Plesko (@miha-plesko)
'''

EXAMPLES = '''
# Pass in a message
- name: Test with a message
  my_new_test_module:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_new_test_module:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_new_test_module:
    name: fail me
'''

RETURN = '''
original_message:
    description: The original name param that was passed in
    type: str
message:
    description: The output message that the sample module generates
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url
from ansible.module_utils._text import to_native

import json
import os
import time


class NuageX(object):
    def __init__(self, module, username, password):
        self.module = module
        self.username = username
        self.password = password
        self._token = None
        self.URL = 'https://experience.nuagenetworks.net/api{path}'

    def token(self):
        if not self._token:
            response, info = fetch_url(
                module=self.module,
                url=self.URL.format(path='/auth/login'),
                headers={'Content-Type': 'application/json'},
                method='POST',
                data=self.module.jsonify({
                    'username': self.username,
                    'password': self.password
                })
            )
            if info['status'] != 200:
                self.module.fail_json(
                    msg='Invalid NuageX credentials (username={}, password=*****)'.format(self.username)
                )
            content = json.loads(to_native(response.read()))
            self._token = content.get('accessToken')
        return self._token

    def lab_by_name(self, name):
        labs = self._api_json('/labs?name={}'.format(name))
        return NuageLab.from_json(labs[0]) if labs else None

    def create_lab(self, name):
        lab_data = self._api_json('/labs', method='POST', data={
            'name': name,
            'template': '5b1ea8267c4dd10001279c31',
            'services': [],
            'networks': [],
            'servers': [],
            'expires': '0001-01-01T00:00:00Z',  # will default to 4.5 days from now
            'reason': 'Created by Ansible'
        })
        return NuageLab.from_json(lab_data)

    def create_lab_sync(self, name):
        self.create_lab(name)
        return self.wait_lab(name)

    def wait_lab(self, name, desired_state='present', retries=20, interval_seconds=5):
        for i in range(retries):
            lab = self.lab_by_name(name)
            if desired_state == 'present' and lab and lab.is_runnung:
                return lab
            elif desired_state == 'absent' and lab is None:
                return True
            time.sleep(interval_seconds)
        return False

    def delete_lab(self, lab):
        self._api('/labs/{}'.format(lab.id), method='DELETE')

    def delete_lab_sync(self, lab):
        self.delete_lab(lab)
        return self.wait_lab(lab.name, desired_state='absent')

    def _api_json(self, path, method='GET', data=None):
        return json.loads(self._api(path, method=method, data=data))

    def _api(self, path, method='GET', data=None):
        data = self.module.jsonify(data) if data is not None else None

        response, info = fetch_url(
            module=self.module,
            url=self.URL.format(path=path),
            headers={
                'Authorization': 'Bearer {}'.format(self.token()),
                'Content-Type': 'application/json'
            },
            method=method,
            data=data
        )
        if not 200 <= info['status'] < 300:
            self.module.fail_json(msg='HTTP error {} {}'.format(info['status'], info['msg']))
        return to_native(response.read())


class NuageLab(object):
    def __init__(self, name, id, status, address, password):
        self.name = name
        self.id = id
        self.status = status
        self.address = address
        self.password = password

    def __str__(self):
        return 'NuageLab (id={id}, name={name}, address={address}, password={password})'.format(
            id=self.id, name=self.name, address=self.address, password=self.password)

    @staticmethod
    def from_json(data):
        return NuageLab(
            data.get('name'),
            data.get('_id'),
            data.get('status'),
            data.get('externalIP'),
            data.get('password'),
        )

    @property
    def as_json(self):
        return {
            'lab_id': self.id,
            'lab_name': self.name,
            'lab_address': self.address,
            'lab_password': self.password,
        }

    @property
    def is_runnung(self):
        return self.status == 'started'


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
        nuagex_auth=dict(type='dict', default={
            'username': os.environ.get('NUX_USERNAME'),
            'password': os.environ.get('NUX_PASSWORD')
        }),
    )

    result = dict(
        changed=False,
        lab_id='',
        lab_name='',
        lab_address='',
        lab_password=''
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    lab_name = module.params.get('name')
    desired_state = module.params.get('state')
    username = module.params.get('nuagex_auth', {}).get('username')
    password = module.params.get('nuagex_auth', {}).get('password')

    if not username:
        module.fail_json(msg='Missing username in nuagex_auth variable.')
    if not password:
        module.fail_json(msg='Missing password in nuagex_auth variable.')

    nux = NuageX(module, username, password)

    # Fail early on invalid credentials
    nux.token()

    # Fetch current state regardless what we'll be doing later
    lab = nux.lab_by_name(lab_name)

    # Perform actions based on drift between desired and current state
    if desired_state == 'present' and lab and lab.is_runnung:
        result.update(lab.as_json)
    elif desired_state == 'present' and lab:  # recreate erroring lab
        result['changed'] = True
        if not module.check_mode:
            nux.delete_lab_sync(lab)
            lab = nux.create_lab_sync(lab_name)
            result.update(lab.as_json)
    elif desired_state == 'present':
        result['changed'] = True
        if not module.check_mode:
            lab = nux.create_lab_sync(lab_name)
            result.update(lab.as_json)
    elif desired_state == 'absent' and lab:
        result['changed'] = True
        if not module.check_mode:
            nux.delete_lab_sync(lab)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
