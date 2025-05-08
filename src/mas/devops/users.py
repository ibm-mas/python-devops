# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import requests
import logging
from kubernetes import client
from openshift.dynamic import DynamicClient
import base64
import atexit
import tempfile
import os
import time
import re


class MASUserUtils():
    '''
    A collection of utilities for interacting with the MAS Core V3 User APIs and related APIs.
    Each instance of this class is tied to a specific MAS instance and workspace ID.
    '''

    MAXADMIN = "MAXADMIN"

    def __init__(self, mas_instance_id: str, mas_workspace_id: str, k8s_client: client.api_client.ApiClient, coreapi_port: int = 443, admin_dashboard_port: int = 443, manage_api_port: int = 443):
        self.mas_instance_id = mas_instance_id
        self.mas_workspace_id = mas_workspace_id
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.mas_core_namespace = f"mas-{self.mas_instance_id}-core"
        self.manage_namespace = f"mas-{self.mas_instance_id}-manage"

        dyn_client = DynamicClient(k8s_client)
        self.v1_secrets = dyn_client.resources.get(api_version="v1", kind="Secret")

        self._mas_superuser_credentials = None
        self._superuser_auth_token = None

        self.mas_admin_url_internal = f'https://admin-dashboard.{self.mas_core_namespace}.svc.cluster.local:{admin_dashboard_port}'
        self._admin_internal_tls_secret = None
        self._admin_internal_ca_pem_file_path = None

        self.mas_api_url_internal = f'https://coreapi.{self.mas_core_namespace}.svc.cluster.local:{coreapi_port}'
        self._core_internal_tls_secret = None
        self._core_internal_ca_pem_file_path = None

        self.manage_api_url_internal = f'https://{self.mas_instance_id}-{self.mas_workspace_id}.{self.manage_namespace}.svc.cluster.local:{manage_api_port}'
        self._manage_internal_tls_secret = None
        self._manage_internal_ca_pem_file_path = None
        self._manage_internal_client_pem_file_path = None

        self._mas_workspace_application_ids = None

    @property
    def mas_superuser_credentials(self):
        if self._mas_superuser_credentials is None:
            k8s_secret = self.v1_secrets.get(name=f"{self.mas_instance_id}-credentials-superuser", namespace=self.mas_core_namespace)
            self._mas_superuser_credentials = dict(
                username=base64.b64decode(k8s_secret.data["username"]).decode("utf-8"),
                password=base64.b64decode(k8s_secret.data["password"]).decode("utf-8"),
            )
        return self._mas_superuser_credentials

    @property
    def admin_internal_tls_secret(self):
        if self._admin_internal_tls_secret is None:
            self._admin_internal_tls_secret = self.v1_secrets.get(name=f"{self.mas_instance_id}-admindashboard-cert-internal", namespace=self.mas_core_namespace)
        return self._admin_internal_tls_secret

    @property
    def admin_internal_ca_pem_file_path(self):
        if self._admin_internal_ca_pem_file_path is None:
            ca = base64.b64decode(self.admin_internal_tls_secret.data["ca.crt"]).decode('utf-8')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as pem_file:
                pem_file.write(ca.encode())
                pem_file.flush()
                pem_file.close()
                atexit.register(os.remove, pem_file.name)
                self._admin_internal_ca_pem_file_path = pem_file.name
        return self._admin_internal_ca_pem_file_path

    @property
    def core_internal_tls_secret(self):
        if self._core_internal_tls_secret is None:
            self._core_internal_tls_secret = self.v1_secrets.get(name=f"{self.mas_instance_id}-coreapi-cert-internal", namespace=self.mas_core_namespace)
        return self._core_internal_tls_secret

    @property
    def core_internal_ca_pem_file_path(self):
        if self._core_internal_ca_pem_file_path is None:
            ca = base64.b64decode(self.core_internal_tls_secret.data["ca.crt"]).decode('utf-8')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as pem_file:
                pem_file.write(ca.encode())
                pem_file.flush()
                pem_file.close()
                atexit.register(os.remove, pem_file.name)
                self._core_internal_ca_pem_file_path = pem_file.name
        return self._core_internal_ca_pem_file_path

    @property
    def superuser_auth_token(self):
        if self._superuser_auth_token is None:
            self.logger.debug("Getting superuser auth token")
            url = f"{self.mas_admin_url_internal}/logininitial"
            headers = {
                "Content-Type": "application/json"
            }
            querystring = {
                "verify": False
            }
            payload = self.mas_superuser_credentials
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                params=querystring,
                verify=self.admin_internal_ca_pem_file_path
            )
            self._superuser_auth_token = response.json()["token"]
        return self._superuser_auth_token

    @property
    def manage_internal_tls_secret(self):
        if self._manage_internal_tls_secret is None:
            self._manage_internal_tls_secret = self.v1_secrets.get(name=f"{self.mas_instance_id}-internal-manage-tls", namespace=self.manage_namespace)
        return self._manage_internal_tls_secret

    @property
    def manage_internal_client_pem_file_path(self):
        if self._manage_internal_client_pem_file_path is None:
            cert = base64.b64decode(self.manage_internal_tls_secret.data["tls.crt"]).decode('utf-8')
            key = base64.b64decode(self.manage_internal_tls_secret.data["tls.key"]).decode('utf-8')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as pem_file:
                pem_file.write(key.encode())
                pem_file.write(cert.encode())
                pem_file.flush()
                pem_file.close()
                atexit.register(os.remove, pem_file.name)
                self._manage_internal_client_pem_file_path = pem_file.name
        return self._manage_internal_client_pem_file_path

    @property
    def manage_internal_ca_pem_file_path(self):
        if self._manage_internal_ca_pem_file_path is None:
            ca = base64.b64decode(self.manage_internal_tls_secret.data["ca.crt"]).decode('utf-8')
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as pem_file:
                pem_file.write(ca.encode())
                pem_file.flush()
                pem_file.close()
                atexit.register(os.remove, pem_file.name)
                self._manage_internal_ca_pem_file_path = pem_file.name
        return self._manage_internal_ca_pem_file_path

    @property
    def mas_workspace_application_ids(self):
        if self._mas_workspace_application_ids is None:
            self._mas_workspace_application_ids = list(map(lambda ma: ma["id"], self.get_mas_applications_in_workspace()))
        return self._mas_workspace_application_ids

    def get_user(self, user_id):
        self.logger.debug(f"Getting user {user_id}")
        url = f"{self.mas_api_url_internal}/v3/users/{user_id}"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.get(
            url,
            headers=headers,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 404:
            return None

        if response.status_code == 200:
            return response.json()

        raise Exception(f"{response.status_code} {response.text}")

    def get_or_create_user(self, payload):
        '''
        User is identified by payload["id"] field
        If user already exists, return their record. No attempt will be made to update the user if other fields of the payload differ from the existing user.
        Otherwise, the user will be created.

        Example payload:
            {
                "id": user_id,
                "status": {"active": True},
                "username": username,
                "token": password,
                "owner": "local",
                "emails": [
                    {
                        "value": email,
                        "type": "Work",
                        "primary": True
                    }
                ],
                "displayName": display_name,
                "issuer": "local",
                "permissions": {
                    "systemAdmin": True,
                    "userAdmin": True,
                    "apikeyAdmin": True
                },
                "entitlement": {
                    "application": "PREMIUM",
                    "admin": "ADMIN_PREMIUM",
                    "alwaysReserveLicense": True
                },
                "title": title,
                "givenName": given_name,
                "familyName": family_name
            }
        '''
        existing_user = self.get_user(payload["id"])

        if existing_user is not None:
            self.logger.info(f"Existing user {existing_user['id']} found")
            return existing_user

        self.logger.info(f"Creating new user {payload['id']}")

        url = f"{self.mas_api_url_internal}/v3/users"
        querystring = {}
        headers = {
            "Content-Type": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            params=querystring,
            verify=self.core_internal_ca_pem_file_path
        )
        if response.status_code == 201:
            return response.json()

        # if response.status_code == 409:
        #     json = response.json()
        #     if "exception" in json and "message" in json["exception"] and json["exception"]["message"] == "AIUCO1005E":
        #         return None

        raise Exception(f"{response.status_code} {response.text}")

    def update_user(self, payload):
        user_id = payload["id"]
        self.logger.debug(f"Updating user {user_id}")
        url = f"{self.mas_api_url_internal}/v3/users/{user_id}"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.put(
            url,
            headers=headers,
            json=payload,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 200:
            return response.json()

        raise Exception(f"{response.status_code} {response.text}")

    def update_user_display_name(self, user_id, display_name):
        self.logger.debug(f"Updating user display name {user_id} to {display_name}")
        url = f"{self.mas_api_url_internal}/v3/users/{user_id}"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.patch(
            url,
            headers=headers,
            json={
                "displayName": display_name
            },
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 200:
            return response.json()

        raise Exception(f"{response.status_code} {response.text}")

    def link_user_to_local_idp(self, user_id, email_password=False):
        '''
        Checks if user already has a local identity, no-op if so.
        Assumes user exists, raises if not
        '''

        # For the sake of idempotency, check if the user already has a local identity
        user = self.get_user(user_id)
        if user is None:
            raise Exception(f"User {user_id} was not found")

        if "identities" in user and "_local" in user["identities"]:
            self.logger.info(f"User {user_id} already has a local identity")
            return None

        self.logger.info(f"Linking user {user_id} to local IDP (email_password: {email_password})")
        url = f"{self.mas_api_url_internal}/v3/users/{user_id}/idps/local"
        querystring = {
            "emailPassword": email_password
        }
        payload = {
            "idpUserId": user_id,
        }
        headers = {
            "Content-Type": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.put(
            url,
            json=payload,
            headers=headers,
            params=querystring,
            verify=self.core_internal_ca_pem_file_path
        )
        if response.status_code != 200:
            raise Exception(response.text)

        # Important: HTTP 200 output will contain generated user token; DO NOT LOG

        return None

    def get_user_workspaces(self, user_id):
        '''
        Assumes user exists, raises if not.
        '''
        self.logger.debug(f"Getting workspaces for user {user_id}")
        url = f"{self.mas_api_url_internal}/v3/users/{user_id}/workspaces"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.get(
            url,
            headers=headers,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 404:
            raise Exception(f"User {user_id} does not exist")

        if response.status_code == 200:
            return response.json()

        raise Exception(f"{response.status_code} {response.text}")

    def add_user_to_workspace(self, user_id, is_workspace_admin=False):
        '''
        No-op if user is already a member of the workspace. No attempt will be made to update their existing is_workspace_admin flag if it differs.
        '''
        workspaces = self.get_user_workspaces(user_id)
        for workspace in workspaces:
            if "id" in workspace and workspace["id"] == self.mas_workspace_id:
                self.logger.info(f"User {user_id} is already a member of workspace {self.mas_workspace_id}")
                return None

        self.logger.info(f"Adding user {user_id} to {self.mas_workspace_id} (is_workspace_admin: {is_workspace_admin})")
        url = f"{self.mas_api_url_internal}/workspaces/{self.mas_workspace_id}/users/{user_id}"
        querystring = {}
        payload = {
            "permissions": {
                "workspaceAdmin": is_workspace_admin
            }
        }
        headers = {
            "Content-Type": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.put(
            url,
            json=payload,
            headers=headers,
            params=querystring,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 200:
            return None

        raise Exception(f"{response.status_code} {response.text}")

    def get_user_application_permissions(self, user_id, application_id):
        self.logger.debug(f"Getting user {user_id} permissions for application {application_id}")
        url = f"{self.mas_api_url_internal}/workspaces/{self.mas_workspace_id}/applications/{application_id}/users/{user_id}"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.get(
            url,
            headers=headers,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            return None

        raise Exception(f"{response.status_code} {response.text}")

    def set_user_application_permission(self, user_id, application_id, role):
        '''
        No-op if user already has a role established for the application. No attempt will be made to update the role if it differs.
        '''

        existing_permissions = self.get_user_application_permissions(user_id, application_id)

        if existing_permissions is not None:
            self.logger.info(f"User {user_id} already has permissions set for application {application_id}")
            return None

        self.logger.info(f"Setting user {user_id} role for {application_id} to {role}")
        url = f"{self.mas_api_url_internal}/workspaces/{self.mas_workspace_id}/applications/{application_id}/users/{user_id}"
        querystring = {}
        payload = {
            "role": role
        }
        headers = {
            "Content-Type": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.put(
            url,
            json=payload,
            headers=headers,
            params=querystring,
            verify=self.core_internal_ca_pem_file_path
        )

        if response.status_code == 200:
            return None

        raise Exception(f"{response.status_code} {response.text}")

    def check_user_sync(self, user_id, application_id, timeout_secs=60 * 10, retry_interval_secs=5):
        t_end = time.time() + timeout_secs
        self.logger.info(f"Awaiting user {user_id} sync status \"SUCCESS\" for app {application_id}: {t_end - time.time():.2f} seconds remaining")
        while time.time() < t_end:
            user = self.get_user(user_id)

            if "applications" not in user or application_id not in user["applications"] or "sync" not in user["applications"][application_id] or "state" not in user["applications"][application_id]["sync"]:
                self.logger.warning(f"User {user_id} does not have any sync state for application {application_id}, triggering resync")
                self.resync_users([user_id])
                time.sleep(retry_interval_secs)
            else:
                sync_state = user["applications"][application_id]["sync"]["state"]
                if sync_state == "SUCCESS":
                    return
                elif sync_state == "ERROR":
                    self.logger.warning(f"User {user_id} sync state for {application_id} was {sync_state}, triggering resync")
                    self.resync_users([user_id])
                    time.sleep(retry_interval_secs)
                else:
                    self.logger.info(f"User {user_id} sync has not been completed yet for app {application_id} (currrently {sync_state}): {t_end - time.time():.2f} seconds remaining")
                time.sleep(retry_interval_secs)
        raise Exception(f"User {user_id} sync failed to complete for app within {timeout_secs} seconds")

    def resync_users(self, user_ids):
        self.logger.info(f"Issuing resync request(s) for user(s) {user_ids}")

        # The "/v3/users/utils/resync" API is only available in MAS Core >= 9.1 (coreapi >= 25.2.3)
        # Until it is available in all supported versions of MAS,
        # we instead perform a no-op update to the user to achieve the same effect
        # (the "update user profile" API is used as this is this allows us to isolate the displayName field,
        # which reduces the impact of concurrent updates leading to race conditions)

        for user_id in user_ids:
            user = self.get_user(user_id)
            self.update_user_display_name(user_id, user["displayName"])

    def create_or_get_manage_api_key_for_user(self, user_id, temporary=False):
        '''
        Get singleton API for user_id if it already exists, create it if not
        if temporary is True AND we created the API key, delete it on exit
        '''
        self.logger.debug(f"Attempting to create Manage API Key for user {user_id}")
        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapiapikey"
        querystring = {
            "ccm": 1,
            "lean": 1,
        }

        payload = {
            "expiration": -1,
            "userid": user_id
        }
        headers = {
            "Content-Type": "application/json",
        }
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            params=querystring,
            verify=self.manage_internal_ca_pem_file_path,
            cert=self.manage_internal_client_pem_file_path,
        )

        if response.status_code == 400:
            # Assisted by watsonx Code Assistant
            try:
                error_json = response.json()
            except ValueError:
                raise Exception(f"{response.status_code} {response.text}")

            if "Error" in error_json and "reasonCode" in error_json["Error"] and error_json["Error"]["reasonCode"] == "BMXAA10051E":
                # BMXAA10051E - Only one API key allowed per user.
                self.logger.info(f"Reusing existing Manage API Key for user {user_id}")
                pass
            else:
                # any other 400 error is unexpected
                raise Exception(f"{response.status_code} {response.text}")

        elif response.status_code == 201:
            self.logger.info(f"Creating new Manage API Key for user {user_id}")
        else:
            # any other status code is unexpected
            raise Exception(f"{response.status_code} {response.text}")

        # otherwise, retrieve the apikey (either it already existed, or we just created it)

        apikey = self.get_manage_api_key_for_user(user_id)
        if apikey is None:
            # either create call reported that apikey already exists, or we created the api key
            # so we expect the get call to find it
            raise Exception("API key was unexpectedly not found")

        if temporary and response.status_code == 201:
            atexit.register(self.delete_manage_api_key, apikey)

        return apikey

    def get_manage_api_key_for_user(self, user_id):
        self.logger.debug(f"Getting Manage API Key for user {user_id}")
        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapiapikey"
        querystring = {
            "ccm": 1,
            "lean": 1,
            "oslc.select": "*",
            "oslc.where": f"userid=\"{user_id}\"",
        }
        headers = {
            "Accept": "application/json",
        }

        response = requests.get(
            url,
            headers=headers,
            params=querystring,
            verify=self.manage_internal_ca_pem_file_path,
            cert=self.manage_internal_client_pem_file_path
        )

        if response.status_code == 200:
            json = response.json()

            if "member" in json and len(json["member"]) > 0:
                return json["member"][0]

            return None

        raise Exception(f"{response.status_code} {response.text}")

    def delete_manage_api_key(self, manage_api_key):
        self.logger.info(f"Deleting Manage API Key for user {manage_api_key['userid']}")

        # extract the apikey's identifier from the href
        match = re.search(r'\/maximo\/api\/os\/mxapiapikey\/(.*)', manage_api_key['href'])
        if match is None:
            raise Exception(f"Could not parse API Key href: {manage_api_key['href']}")

        id = match.group(1)

        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapiapikey/{id}"
        querystring = {
            "ccm": 1,
            "lean": 1,
        }
        headers = {
            "Accept": "application/json",
        }
        response = requests.delete(
            url,
            headers=headers,
            params=querystring,
            verify=self.manage_internal_ca_pem_file_path,
            cert=self.manage_internal_client_pem_file_path,
        )

        if response.status_code != 204 and response.status_code != 404:
            raise Exception(f"{response.status_code} {response.text}")

    def get_manage_group_id(self, group_name, manage_api_key):
        self.logger.debug(f"Getting ID for Manage group with name {group_name}")
        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapigroup"
        querystring = {
            "ccm": 1,
            "lean": 1,
            "oslc.select": "maxgroupid",
            "oslc.where": f"groupname=\"{group_name}\"",
        }
        headers = {
            "Accept": "application/json",
            "apikey": manage_api_key["apikey"],  # <--- careful, don't log headers as-is (apikey is sensitive)
        }
        response = requests.get(
            url,
            headers=headers,
            params=querystring,
            verify=self.manage_internal_ca_pem_file_path,
        )
        if response.status_code != 200:
            raise Exception(f"{response.status_code} {response.text}")

        json = response.json()

        if "member" in json and len(json["member"]) > 0 and "maxgroupid" in json["member"][0]:
            return json["member"][0]['maxgroupid']

        return None

    def is_user_in_manage_group(self, group_name, user_id, manage_api_key):
        self.logger.debug(f"Checking if {user_id} is a member of Manage group with name {group_name}")

        group_id = self.get_manage_group_id(group_name, manage_api_key)

        if group_id is None:
            raise Exception(f"No Manage group found with name {group_name}")

        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapigroup/{group_id}/groupuser"
        querystring = {
            "lean": 1,
            "oslc.where": f"userid=\"{user_id}\"",
        }
        headers = {
            "Accept": "application/json",
            "apikey": manage_api_key["apikey"],  # <--- careful, don't log headers as-is (apikey is sensitive)
        }

        response = requests.get(
            url,
            headers=headers,
            params=querystring,
            verify=self.manage_internal_ca_pem_file_path,
        )

        if response.status_code == 200:
            json = response.json()
            return "member" in json and len(json["member"]) > 0

        raise Exception(f"{response.status_code} {response.text}")

    def add_user_to_manage_group(self, user_id, group_name, manage_api_key):
        '''
        No-op if user_id is already a member of the manage security group
        '''

        if self.is_user_in_manage_group(group_name, user_id, manage_api_key):
            self.logger.info(f"User {user_id} is already a member of Manage Security Group {group_name}")
            return None

        self.logger.info(f"Adding user {user_id} to Manage group {group_name}")

        group_id = self.get_manage_group_id(group_name, manage_api_key)

        url = f"{self.manage_api_url_internal}/maximo/api/os/mxapigroup/{group_id}"
        querystring = {
            "lean": 1,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "apikey": manage_api_key["apikey"],  # <--- careful, don't log headers as-is (apikey is sensitive)
        }
        payload = {
            "groupuser": [
                {
                    "userid": f"{user_id}"
                }
            ]
        }
        response = requests.post(
            url,
            headers=headers,
            params=querystring,
            json=payload,
            verify=self.manage_internal_ca_pem_file_path,
        )
        if response.status_code == 204:
            return None

        raise Exception(f"{response.status_code} {response.text}")

    def get_mas_applications_in_workspace(self):
        self.logger.debug(f"Getting MAS Applications in workspace {self.mas_workspace_id}")
        url = f"{self.mas_api_url_internal}/workspaces/{self.mas_workspace_id}/applications"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.get(
            url,
            headers=headers,
            verify=self.core_internal_ca_pem_file_path
        )
        if response.status_code == 200:
            return response.json()
        raise Exception(f"{response.status_code} {response.text}")

    def get_mas_application_availability(self, mas_application_id):
        self.logger.debug(f"Getting availability of MAS Application {mas_application_id} in workspace {self.mas_workspace_id}")
        url = f"{self.mas_api_url_internal}/workspaces/{self.mas_workspace_id}/applications/{mas_application_id}"
        headers = {
            "Accept": "application/json",
            "x-access-token": self.superuser_auth_token
        }
        response = requests.get(
            url,
            headers=headers,
            verify=self.core_internal_ca_pem_file_path
        )
        if response.status_code == 200:
            return response.json()
        raise Exception(f"{response.status_code} {response.text}")

    def await_mas_application_availability(self, mas_application_id, timeout_secs=60 * 10, retry_interval_secs=5):
        t_end = time.time() + timeout_secs
        self.logger.info(f"Waiting for {mas_application_id} to become ready and available: {t_end - time.time():.2f} seconds remaining")
        while time.time() < t_end:
            app = self.get_mas_application_availability(mas_application_id)
            if "available" in app and "ready" in app and app["ready"] and app["available"]:
                return
            else:
                self.logger.info(f"{mas_application_id} is not ready or available, retry in {retry_interval_secs} seconds: {t_end - time.time():.2f} seconds remaining")
                time.sleep(retry_interval_secs)
        raise Exception(f"{mas_application_id} did not become ready and available in time, aborting")

    def parse_initial_users_from_aws_secret_json(self, secret_json):
        primary = []
        secondary = []
        for (email, csv) in secret_json.items():
            values = csv.split(",")

            if len(values) != 3:
                raise Exception(f"Wrong number of CSV values for {email} (expected 3 but got {len(values)})")

            user_type = values[0].strip()
            given_name = values[1].strip()
            family_name = values[2].strip()

            user = {
                "email": email,
                "given_name": given_name,
                "family_name": family_name
            }
            if user_type == "primary":
                primary.append(user)
            elif user_type == "secondary":
                secondary.append(user)
            else:
                raise Exception(f"Unknown user type for {email}: {user_type}")

        initial_users = {
            "users": {
                "primary": primary,
                "secondary": secondary
            }
        }
        return initial_users

    def create_initial_users_for_saas(self, initial_users):

        # Validate input
        if "users" not in initial_users:
            raise Exception("expected top-level key 'users' not found")
        users = initial_users["users"]
        if "primary" not in users:
            raise Exception("expected key 'users.primary' not found")
        primary_users = users["primary"]
        if type(primary_users) is not list:
            raise Exception("'users.primary' is not a list")
        if "secondary" not in users:
            raise Exception("expected key 'users.secondary' not found")
        secondary_users = users["secondary"]
        if type(secondary_users) is not list:
            raise Exception("'users.secondary' is not a list")

        if len(primary_users) == 0 and len(secondary_users) == 0:
            self.logger.info("No users left to sync, nothing to do")
            return {"completed": [], "failed": []}

        # before we do anything, let's check all MAS applications are ready
        for mas_application_id in self.mas_workspace_application_ids:
            self.await_mas_application_availability(mas_application_id)

        completed = []
        failed = []

        for primary_user in primary_users:
            self.logger.info("")
            try:
                self.logger.info(f"Syncing primary user {primary_user['email']}")
                self.create_initial_user_for_saas(primary_user, "PRIMARY")
                completed.append(primary_user)
                self.logger.info(f"Completed sync of primary user {primary_user['email']}")
            except Exception as e:
                self.logger.error(f"Sync of primary user {primary_user['email']} failed: {str(e)}")
                failed.append(primary_user)

        for secondary_user in secondary_users:
            self.logger.info("")
            try:
                self.logger.info("")
                self.logger.info(f"Syncing secondary user {secondary_user['email']}")
                self.create_initial_user_for_saas(secondary_user, "SECONDARY")
                completed.append(secondary_user)
                self.logger.info(f"Completed sync of secondary user {secondary_user['email']}")
            except Exception as e:
                self.logger.error(f"Sync of secondary user {secondary_user['email']} failed: {str(e)}")
                failed.append(secondary_user)
            self.logger.info("")

        return {
            "completed": completed,
            "failed": failed
        }

    def create_initial_user_for_saas(self, user, user_type):
        if "email" not in user:
            raise Exception("'email' not found in at least one of the user defs")
        if "given_name" not in user:
            raise Exception("'given_name' not found in at least one of the user defs")
        if "family_name" not in user:
            raise Exception("'family_name' not found in at least one of the user defs")

        user_email = user["email"]
        user_given_name = user["given_name"]
        user_family_name = user["family_name"]

        user_id = user_email
        username = user_email
        # display_name = re.search('^([^@]+)@', user_email).group(1) # local part of the email
        display_name = f"{user_given_name} {user_family_name}"

        # Set user permissions and entitlements based on requested user_type
        if user_type == "PRIMARY":
            permissions = {
                "systemAdmin": False,
                "userAdmin": True,
                "apikeyAdmin": False
            }
            entitlement = {
                "application": "PREMIUM",
                "admin": "ADMIN_BASE",
                "alwaysReserveLicense": True
            }
            is_workspace_admin = True
            application_role = "ADMIN"
            # TODO: check which security groups primary users should be members of
            manage_security_groups = ["MAXADMIN"]
        elif user_type == "SECONDARY":
            permissions = {
                "systemAdmin": False,
                "userAdmin": False,
                "apikeyAdmin": False
            }
            entitlement = {
                "application": "BASE",
                "admin": "NONE",
                "alwaysReserveLicense": True
            }
            is_workspace_admin = False
            application_role = "USER"
            # TODO: check which security groups secondary users should be members of
            manage_security_groups = []
        else:
            raise Exception(f"Unsupported user_type: {user_type}")

        user_def = {
            "id": user_id,
            "status": {"active": True},
            "username": username,
            "owner": "local",
            "emails": [
                {
                    "value": user_email,
                    "type": "Work",
                    "primary": True
                }
            ],
            "displayName": display_name,
            "issuer": "local",
            "permissions": permissions,
            "entitlement": entitlement,
            "givenName": user_given_name,
            "familyName": user_family_name
        }

        self.get_or_create_user(user_def)
        self.link_user_to_local_idp(user_id, email_password=True)
        self.add_user_to_workspace(user_id, is_workspace_admin=is_workspace_admin)

        for mas_application_id in self.mas_workspace_application_ids:
            self.await_mas_application_availability(mas_application_id)
            if mas_application_id == "manage":
                # special case for manage; role is always "MANAGEUSER"
                role = "MANAGEUSER"
            else:
                # otherwise grant the user the appropriate role for their user_type
                role = application_role
            self.set_user_application_permission(user_id, mas_application_id, role)

        for mas_application_id in self.mas_workspace_application_ids:
            self.check_user_sync(user_id, mas_application_id)

        if len(manage_security_groups) > 0 and "manage" in self.mas_workspace_application_ids:
            maxadmin_manage_api_key = self.create_or_get_manage_api_key_for_user(MASUserUtils.MAXADMIN, temporary=True)
            for manage_security_group in manage_security_groups:
                self.add_user_to_manage_group(user_id, manage_security_group, maxadmin_manage_api_key)
