#!/usr/bin/python

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: nuagex_lab
short_description: Ensure a running NuageX sandbox (https://experience.nuagenetworks.net)
version_added: "2.7"
description:
    - "Ensures that a NuageX lab by specific name is provisioned or decomissioned."
options:
    naugex_auth:
        description:
            - Dict with the authentication information required to connect to the NuageX environment.
            - Requires a I(username) parameter (example 'user01').
            - Requires a I(password) parameter (example 'my-password01').
            - You can omit the I(nuagex_auth) parameter and rely on NUX_USERNAME and NUX_PASSWORD environment vars
        required: false
        default: attempts to fetch credentials from environment
    name:
        description:
            - Desired NuageX lab name
        required: true
    template:
        description:
            - Which template to provision lab from (example "Nuage Networks 5.3.1 - VSP")
            - If template name is not provided, then first template found is taken after sorting them by name
            - Must be template name, not ID
        required: false
    state:
        description: Can one of [present,absent]

author:
    - Miha Plesko (@miha-plesko)
'''

EXAMPLES = '''
# Request lab named 'integration-tests', passing credentials as parameters
- name: Request lab running
  nuagex_lab:
    nuagex_auth:
      username: user01
      password: my-password01
    name: integration-tests
    state: present
    
# Request lab named 'integration-tests', passing credentials as environment variables
- name: Request lab running
  nuagex_lab:
    name: integration-tests
    state: present
  environment:
    NUX_USERNAME: user01
    NUX_PASSWORD: my-password01

# Request lab named 'integration-tests', using specific template
- name: Request lab running
  nuagex_lab:
    name: integration-tests
    state: present
    template: Nuage Networks 5.3.1 - VSP
    
# Ensure lab named 'integration-tests' is destroyed
- name: Request lab destroyed
  nuagex_lab:
    name: integration-tests
    state: absent
    
# Obtain lab access data and print it
- name: Obtain lab access data
  nuagex_lab:
    name: integration-tests
    template: Nuage Networks 5.3.1 - VSP
  register: lab  
- name: Print lab access data
  debug: var=lab
# ok: [localhost] => {
#    "lab": {
#        "lab_name": "integration-tests", 
#        "lab_id": "aaaaaabbbbbbccccccdddddd", 
#        "lab_ip": "1.2.3.4", 
#        "lab_web": {
#            "address": "https://1.2.3.4:443", 
#            "org": "org1", 
#            "user": "user1",
#            "password": "the-password"
#        },
#        "lab_amqp": {
#            "address": "amqp://1.2.3.4:5672",
#            "password": "the-password", 
#            "user": "the-user@system"
#        }, 
#    }
# }
'''

RETURN = '''
lab_name:
    description: Name of the NuageX lab
    type: str
lab_id:
    description: ID of the NuageX lab
    type: str
lab_ip:
    description: IPv4 address of the NuageX lab
    type: str
lab_web:
    description: Dict containing connectivity information to NuageX web interface
    fields:
    - address e.g. "https://1.2.3.4:443"
    - org e.g "org1"
    - user e.g. "user1"
    - password e.g. "the-password"
    type: dict
lab_amqp:
    description: Dict containing connectivity information to NuageX AMQP eventing interface
    fields:
    - address e.g. "amqp://1.2.3.4:5672"
    - user e.g. "the-user@system"
    - password e.g. "the-password"
    type: dict
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

    def first_template(self, name=None):
        """
        Get template by name if name is given, else first template found.
        :param name: Name of the tamplate. If None, first template available will be taken.
        :return: template instance or None
        """
        templates = self._api_json('/templates')
        if name:
            templates = [t for t in templates if t.get('name') == name]
        templates = sorted(templates, key=lambda t: t['name'])
        return NuageTemplate.from_json(templates[0]) if templates else None

    def first_template_or_fail(self, name=None):
        template = self.first_template(name=name)
        if not template and name:
            self.module.fail_json(msg='Template named "{}" does not exist'.format(name))
        elif not template:
            self.module.fail_json(msg='No available template found on NuageX')
        return template

    def create_lab(self, name, template):
        lab_data = self._api_json('/labs', method='POST', data={
            'name': name,
            'template': template.id,
            'services': [],
            'networks': [],
            'servers': [],
            'expires': '0001-01-01T00:00:00Z',  # will default to 4.5 days from now
            'reason': 'Created by Ansible'
        })
        return NuageLab.from_json(lab_data)

    def create_lab_sync(self, name, template):
        self.create_lab(name, template)
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
    def __init__(self, name, id, status, ip, password):
        self.name = name
        self.id = id
        self.status = status
        self.ip = ip
        self.password = password

    def __str__(self):
        return 'NuageLab (id={id}, name={name}, ip={ip}, password={password})'.format(
            id=self.id, name=self.name, ip=self.ip, password=self.password)

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
            'lab_ip': self.ip,
            'lab_web': {
                'address': 'https://{}:8443'.format(self.ip),
                'user': 'admin',
                'password': self.password,
                'org': 'csp'
            },
            'lab_amqp': {
                'address': 'amqp://{}:5672'.format(self.ip),
                'user': 'jmsuser@system',
                'password': 'jmspass'
            }
        }

    @property
    def is_runnung(self):
        return self.status == 'started'


class NuageTemplate(object):
    def __init__(self, name, id):
        self.name = name
        self.id = id

    def __str__(self):
        return 'NuageTemplate (id={id}, name={name})'.format(id=self.id, name=self.name)

    @staticmethod
    def from_json(data):
        return NuageTemplate(
            data.get('name'),
            data.get('_id')
        )


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
        nuagex_auth=dict(type='dict', default={
            'username': os.environ.get('NUX_USERNAME'),
            'password': os.environ.get('NUX_PASSWORD')
        }),
        template=dict(type='str', required=False)
    )

    result = dict(
        changed=False,
        lab_id='',
        lab_name='',
        lab_ip='',
        lab_web={},
        lab_amqp={},
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    lab_name = module.params.get('name')
    template_name = module.params.get('template')
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
            template = nux.first_template_or_fail(template_name)
            lab = nux.create_lab_sync(lab_name, template)
            result.update(lab.as_json)
    elif desired_state == 'present':
        result['changed'] = True
        if not module.check_mode:
            template = nux.first_template_or_fail(template_name)
            lab = nux.create_lab_sync(lab_name, template)
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
