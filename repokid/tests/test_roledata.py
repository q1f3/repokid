#     Copyright 2017 Netflix, Inc.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
import datetime
import time

from dateutil.tz import tzlocal
from mock import patch

import repokid.utils.roledata
from repokid.role import Role


AARDVARK_DATA = {
    "arn:aws:iam::123456789012:role/all_services_used": [
        {"lastAuthenticated": int(time.time()) * 1000,
         "serviceNamespace": "iam"},
        {"lastAuthenticated": int(time.time()) * 1000,
         "serviceNamespace": "s3"}],

    "arn:aws:iam::123456789012:role/unused_ec2": [
        {"lastAuthenticated": int(time.time()) * 1000,
         "serviceNamespace": "iam"},
        {"lastAuthenticated": 0,
         "serviceNamespace": "ec2"}],

    "arn:aws:iam::123456789012:role/young_role": [
        {"lastAuthenticated": int(time.time()) * 1000,
         "serviceNamespace": "iam"},
        {"lastAuthenticated": int(time.time()) * 1000,
         "serviceNamespace": "s3"}]
}

ROLE_POLICIES = {
    'all_services_used': {
            'iam_perms': {
                'Version': '2012-10-17',
                'Statement': [
                    {'Action': ['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy'],
                     'Resource': ['*'],
                     'Effect': 'Allow'}]},

            's3_perms': {
                'Version': '2012-10-17',
                'Statement': [
                    {'Action': ['s3:CreateBucket', 's3:DeleteBucket'],
                     'Resource': ['*'],
                     'Effect': 'Allow'}]}},
    'unused_ec2': {
            'iam_perms': {
                'Version': '2012-10-17',
                'Statement': [
                    {'Action': ['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy'],
                     'Resource': ['*'],
                     'Effect': 'Allow'}]},

            'ec2_perms': {
                'Version': '2012-10-17',
                'Statement': [
                    {'Action': ['ec2:AllocateHosts', 'ec2:AssociateAddress'],
                     'Resource': ['*'],
                     'Effect': 'Allow'}]}}
}

ROLES = [
    {
        "Arn": "arn:aws:iam::123456789012:role/all_services_used",
        "CreateDate": datetime.datetime(2017, 1, 31, 12, 0, 0, tzinfo=tzlocal()),
        "RoleId": "AROAABCDEFGHIJKLMNOPA",
        "RoleName": "all_services_used",
        "Active": True
    },
    {
        "Arn": "arn:aws:iam::123456789012:role/unused_ec2",
        "CreateDate": datetime.datetime(2017, 1, 31, 12, 0, 0, tzinfo=tzlocal()),
        "RoleId": "AROAABCDEFGHIJKLMNOPB",
        "RoleName": "unused_ec2",
        "Active": True,
    },
    {
        "Arn": "arn:aws:iam::123456789012:role/young_role",
        "CreateDate": datetime.datetime.now(tzlocal()) - datetime.timedelta(5),
        "RoleId": "AROAABCDEFGHIJKLMNOPC",
        "RoleName": "young_role",
        "Active": True,
    },
    {
        "Arn": "arn:aws:iam::123456789012:role/inactive_role",
        "CreateDate": datetime.datetime.now(tzlocal()) - datetime.timedelta(5),
        "RoleId": "AROAABCDEFGHIJKLMNOPD",
        "RoleName": "inactive_role",
        "Active": False,
    }
]


class TestRoledata(object):
    @patch('repokid.utils.roledata.expand_policy')
    @patch('repokid.utils.roledata.get_actions_from_statement')
    @patch('repokid.utils.roledata.all_permissions')
    def test_get_role_permissions(self, mock_all_permissions, mock_get_actions_from_statement, mock_expand_policy):
        test_role = Role(ROLES[0])

        all_permissions = ['ec2:associateaddress', 'ec2:attachvolume', 'ec2:createsnapshot', 's3:createbucket',
                           's3:getobject']

        # empty policy to make sure we get the latest
        test_role.policies = [{'Policy': ROLE_POLICIES['all_services_used']}, {'Policy': ROLE_POLICIES['unused_ec2']}]

        mock_all_permissions.return_value = all_permissions
        mock_get_actions_from_statement.return_value = ROLE_POLICIES['unused_ec2']['ec2_perms']
        mock_expand_policy.return_value = ROLE_POLICIES['unused_ec2']['ec2_perms']

        permissions = repokid.utils.roledata._get_role_permissions(test_role)
        assert permissions == set(ROLE_POLICIES['unused_ec2']['ec2_perms'])

    def test_get_repoable_permissions(self):
        repokid.utils.roledata.CONFIG = {'filter_config': {'AgeFilter': {'minimum_age': 1}}}
        repokid.utils.roledata.IAM_ACCESS_ADVISOR_UNSUPPORTED_SERVICES = ['service_2']
        repokid.utils.roledata.IAM_ACCESS_ADVISOR_UNSUPPORTED_ACTIONS = ['service_1:action_3', 'service_1:action_4']

        permissions = ['service_1:action_1', 'service_1:action_2', 'service_1:action_3', 'service_1:action_4',
                       'service_2:action_1', 'service_3:action_1', 'service_3:action_2', 'service_4:action_1',
                       'service_4:action_2']

        # service_1 and service_2 both used more than a day ago, which is outside of our test filter for age
        aa_data = [{'serviceNamespace': 'service_1', 'lastAuthenticated': (time.time() - 90000) * 1000},
                   {'serviceNamespace': 'service_2', 'lastAuthenticated': (time.time() - 90000) * 1000},
                   {'serviceNamespace': 'service_3', 'lastAuthenticated': time.time() * 1000}]

        no_repo_permissions = {'service_4:action_1': time.time()-1, 'service_4:action_2': time.time()+1000}

        repoable_permissions = repokid.utils.roledata._get_repoable_permissions(permissions, aa_data,
                                                                                no_repo_permissions)
        # service_1:action_3 and action_4 are unsupported actions, service_2 is an unsupported service, service_3
        # was used too recently, service_4 action 2 is in no_repo_permissions and not expired
        assert repoable_permissions == set(['service_1:action_1', 'service_1:action_2', 'service_4:action_1'])

    @patch('repokid.utils.roledata._get_role_permissions')
    @patch('repokid.utils.roledata._get_repoable_permissions')
    def test_calculate_repo_scores(self, mock_get_repoable_permissions, mock_get_role_permissions):
        roles = [Role(ROLES[0]), Role(ROLES[1]), Role(ROLES[2])]
        roles[0].disqualified_by = []
        roles[0].aa_data = 'some_aa_data'

        # disqualified by a filter
        roles[1].policies = [{'Policy': ROLE_POLICIES['unused_ec2']}]
        roles[1].disqualified_by = ['some_filter']
        roles[1].aa_data = 'some_aa_data'

        # no AA data
        roles[2].policies = [{'Policy': ROLE_POLICIES['all_services_used']}]
        roles[2].disqualified_by = []
        roles[2].aa_data = None

        mock_get_role_permissions.side_effect = [['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy',
                                                  'ec2:AllocateHosts', 'ec2:AssociateAddress'],
                                                 ['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy'],
                                                 ['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy']]

        mock_get_repoable_permissions.side_effect = [set(['iam:AddRoleToInstanceProfile', 'iam:AttachRolePolicy'])]

        repokid.utils.roledata._calculate_repo_scores(roles)

        assert roles[0].repoable_permissions == 2
        assert roles[0].repoable_services == ['iam']
        assert roles[1].repoable_permissions == 0
        assert roles[1].repoable_services == []
        assert roles[2].repoable_permissions == 0
        assert roles[2].repoable_services == []

    def test_get_repoed_policy(self):
        policies = ROLE_POLICIES['all_services_used']
        repoable_permissions = set(['iam:addroletoinstanceprofile', 'iam:attachrolepolicy', 's3:createbucket'])

        rewritten_policies, empty_policies = repokid.utils.roledata._get_repoed_policy(policies, repoable_permissions)

        assert rewritten_policies == {'s3_perms': {'Version': '2012-10-17',
                                                   'Statement': [{'Action': ['s3:deletebucket'],
                                                                  'Resource': ['*'],
                                                                  'Effect': 'Allow'}]}}
        assert empty_policies == ['iam_perms']

    def test_find_newly_added_permissions(self):
        old_policy = ROLE_POLICIES['all_services_used']
        new_policy = ROLE_POLICIES['unused_ec2']

        new_perms = repokid.utils.roledata.find_newly_added_permissions(old_policy, new_policy)
        assert new_perms == set(['ec2:allocatehosts', 'ec2:associateaddress'])
