![coverage](https://img.shields.io/badge/python-2.7%20|%203.6-blue.svg)

# Ansible role: xlab_si.nuagex
This role provides an Ansible module `nuagex_lab` which ensures that desired
[NuageX sandbox](https://experience.nuagenetworks.net) is there for you.

## Requirements & Dependencies
There are no specific requirements or dependencies for this role. Just point to
it in your playbook and enjoy the awesomeness of the `nuagex_lab:` module.

## Example Playbook
Suppose we want to have NuageX sandbox named 'My Sandbox' available. We don't
care what lab template is used so first available will be taken, alphabetically
sorted:

```yaml
- hosts: localhost
  connection: local
  gather_facts: no
  roles:
    - xlab_si.nuagex  # contains nuagex_lab: module
  tasks:
    - name: Ensure NuageX lab named 'My Sandbox' is running
      nuagex_lab:
        name: My Sandbox
        state: present
      register: lab
```

Playbook assumes there are `NUX_USERNAME` and `NUX_PASSWORD` environment variables
defined upon playbook execution to authenticate against NuageX service. It's also
possible to authenticate by means of `{{ nuagex_auth }}` dict variable, see module
documentation for examples.

Module result contains all the connection information (endpoints, ports, credentials
etc.) needed to use the NuageX lab.

Now suppose we want to make sure the NuageX sandbox named 'My Sandbox' is
destroyed:

```yaml
- hosts: localhost
  connection: local
  gather_facts: no
  roles:
    - xlab_si.nuagex  # contains nuagex_lab: module
  tasks:
    - name: Ensure NuageX lab named 'My Sandbox' is running
      nuagex_lab:
        name: My Sandbox
        state: absent
```

## Module documentation
Please consult `nuagex_lab:` module documentation for supported module arguments.
Since this module isn't part of global Ansible modules, you need to access
documentation locally as opposed to web docs:

```
ansible-doc nuagex_lab -M roles/xlab_si.nuagex/library
```

or read it directly from the [module soruce code](./library/nuagex_lab.py).

 


