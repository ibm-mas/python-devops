#!/usr/bin/env python3

# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

import os
from slack_sdk import WebClient
from slack_sdk.web.slack_response import SlackResponse
from kubernetes import client, config
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class SlackUtilMeta(type):
    def __init__(cls, *args, **kwargs):
        # Exposed by the client() property method
        cls._client = None

    @property
    def client(cls) -> WebClient:
        """
        Get or create the Slack WebClient instance.

        Lazily initializes the Slack client using the SLACK_TOKEN environment variable.

        Returns:
            WebClient: The Slack WebClient instance

        Raises:
            Exception: If SLACK_TOKEN environment variable is not set
        """
        if cls._client is not None:
            return cls._client
        else:
            SLACK_TOKEN = os.getenv("SLACK_TOKEN")
            if SLACK_TOKEN is None:
                logger.warning("SLACK_TOKEN is not set")
                raise Exception("SLACK_TOKEN is not set")
            else:
                cls._client = WebClient(token=SLACK_TOKEN)
                return cls._client

    def postMessageBlocks(
        cls, channelList: str | list[str], messageBlocks: list, threadId: str = None
    ) -> SlackResponse | list[SlackResponse]:
        """
        Post a message with block formatting to one or more Slack channels.

        Parameters:
            channelList (str | list[str]): Single channel ID/name or list of channel IDs/names
            messageBlocks (list): List of Slack block kit elements defining the message structure
            threadId (str, optional): Thread timestamp to post as a reply. Defaults to None.

        Returns:
            SlackResponse | list[SlackResponse]: Single response if one channel, list of responses if multiple channels

        Raises:
            Exception: If message posting fails
        """
        responses: list[SlackResponse] = []

        if isinstance(channelList, str):
            channelList = [channelList]
        for channel in channelList:
            try:
                if threadId is None:
                    logger.debug(
                        f"Posting {len(messageBlocks)} block message to {channel} in Slack"
                    )
                    response = cls.client.chat_postMessage(
                        channel=channel,
                        blocks=messageBlocks,
                        text="Summary text unavailable",
                        mrkdwn=True,
                        parse="none",
                        unfurl_links=False,
                        unfurl_media=False,
                        link_names=True,
                        as_user=True,
                    )
                else:
                    logger.debug(
                        f"Posting {len(messageBlocks)} block message to {channel} on thread {threadId} in Slack"
                    )
                    response = cls.client.chat_postMessage(
                        channel=channel,
                        thread_ts=threadId,
                        blocks=messageBlocks,
                        text="Summary text unavailable",
                        mrkdwn=True,
                        parse="none",
                        unfurl_links=False,
                        unfurl_media=False,
                        link_names=True,
                        as_user=True,
                    )

                if not response["ok"]:
                    logger.warning(response.data)
                    logger.warning("Failed to call Slack API")
                responses.append(response)
            except Exception as e:
                logger.error(f"Fail to send a message to {channel}: {e}")
                raise

        return responses if len(responses) > 1 else responses[0]

    def postMessageText(
        cls,
        channelList: str | list[str],
        message: str,
        attachments=None,
        threadId: str = None,
    ) -> SlackResponse | list[SlackResponse]:
        """
        Post a plain text message to one or more Slack channels.

        Parameters:
            channelList (str | list[str]): Single channel ID/name or list of channel IDs/names
            message (str): The text message to post
            attachments (list, optional): List of message attachments. Defaults to None.
            threadId (str, optional): Thread timestamp to post as a reply. Defaults to None.

        Returns:
            SlackResponse | list[SlackResponse]: Single response if one channel, list of responses if multiple channels

        Raises:
            Exception: If message posting fails
        """
        responses: list[SlackResponse] = []

        if isinstance(channelList, str):
            channelList = [channelList]

        for channel in channelList:
            if threadId is None:
                logger.debug(f"Posting message to {channel} in Slack")
                response = cls.client.chat_postMessage(
                    channel=channel,
                    text=message,
                    attachments=attachments,
                    mrkdwn=True,
                    parse="none",
                    unfurl_links=False,
                    unfurl_media=False,
                    link_names=True,
                    as_user=True,
                )
            else:
                logger.debug(
                    f"Posting message to {channel} on thread {threadId} in Slack"
                )
                response = cls.client.chat_postMessage(
                    channel=channel,
                    thread_ts=threadId,
                    text=message,
                    attachments=attachments,
                    mrkdwn=True,
                    parse="none",
                    unfurl_links=False,
                    unfurl_media=False,
                    link_names=True,
                    as_user=True,
                )

            if not response["ok"]:
                logger.warning(response.data)
                logger.warning("Failed to call Slack API")
            responses.append(response)

        return responses if len(responses) > 1 else responses[0]

    def createMessagePermalink(
        cls,
        slackResponse: SlackResponse = None,
        channelId: str = None,
        messageTimestamp: str = None,
        domain: str = "ibm-mas",
    ) -> str:
        """
        Create a permanent link to a Slack message.

        Parameters:
            slackResponse (SlackResponse, optional): Slack response object containing channel and timestamp. Defaults to None.
            channelId (str, optional): Channel ID if not using slackResponse. Defaults to None.
            messageTimestamp (str, optional): Message timestamp if not using slackResponse. Defaults to None.
            domain (str, optional): Slack workspace domain. Defaults to "ibm-mas".

        Returns:
            str: Permanent URL to the Slack message

        Raises:
            Exception: If neither slackResponse nor both channelId and messageTimestamp are provided
        """
        if slackResponse is not None:
            channelId = slackResponse["channel"]
            messageTimestamp = slackResponse["ts"]
        elif channelId is None or messageTimestamp is None:
            raise Exception(
                "Either channelId and messageTimestamp, or slackReponse params must be provided"
            )

        return f"https://{domain}.slack.com/archives/{channelId}/p{messageTimestamp.replace('.', '')}"

    def updateMessageBlocks(
        cls, channelName: str, threadId: str, messageBlocks: list
    ) -> SlackResponse:
        """
        Update an existing Slack message with new block content.

        Parameters:
            channelName (str): The channel ID or name containing the message
            threadId (str): The timestamp of the message to update
            messageBlocks (list): List of Slack block kit elements for the updated message

        Returns:
            SlackResponse: Response from the Slack API

        Raises:
            Exception: If message update fails
        """
        logger.debug(
            f"Updating {len(messageBlocks)} block message in {channelName} on thread {threadId} in Slack"
        )
        response = cls.client.chat_update(
            channel=channelName,
            ts=threadId,
            blocks=messageBlocks,
            mrkdwn=True,
            parse="none",
            unfurl_links=False,
            unfurl_media=False,
            link_names=True,
            as_user=True,
        )

        if not response["ok"]:
            logger.warning(response.data)
            logger.warning("Failed to call Slack API")
        return response

    def buildHeader(cls, title: str) -> dict:
        """
        Build a header block for a Slack message.

        Parameters:
            title (str): The header text

        Returns:
            dict: Slack block kit header element
        """
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": title, "emoji": True},
        }

    def buildSection(cls, text: str) -> dict:
        """
        Build a section block for a Slack message with markdown text.

        Parameters:
            text (str): The section text (supports markdown formatting)

        Returns:
            dict: Slack block kit section element
        """
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    def buildContext(cls, texts: list) -> dict:
        """
        Build a context block for a Slack message with multiple text elements.

        Parameters:
            texts (list): List of text strings to include in the context

        Returns:
            dict: Slack block kit context element
        """
        elements = []
        for text in texts:
            elements.append({"type": "mrkdwn", "text": text})

        return {"type": "context", "elements": elements}

    def buildDivider(cls) -> dict:
        """
        Build a divider block for a Slack message.

        Returns:
            dict: Slack block kit divider element
        """

    def createThreadConfigMap(
        cls, namespace: str, instanceId: str, pipelineRunName: str
    ) -> bool:
        """
        Create a ConfigMap to store Slack thread information for a pipeline run.

        Parameters:
            namespace (str): Kubernetes namespace for the ConfigMap
            channelId (str): Slack channel ID where the thread was created
            threadId (str): Slack thread timestamp
            instanceId (str): Name of the Mas Instance ID (can be None or empty for update pipeline)

        Returns:
            bool: True if ConfigMap was created successfully, False otherwise
        """
        try:
            # Load Kubernetes configuration
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()
            # For update pipeline (no instance ID), use "update" as identifier
            instance_identifier = instanceId if instanceId else "update"
            configmap_name = f"slack-thread-{instance_identifier}-{pipelineRunName}"
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=configmap_name, namespace=namespace),
                data={
                    "pipelineName": pipelineRunName,
                    "instanceId": instanceId,
                    "startTime": datetime.now(timezone.utc),
                },
            )
            v1.create_namespaced_config_map(namespace=namespace, body=configmap)
            logger.info(f"Created ConfigMap {configmap_name} in namespace {namespace}")
            return True
        except Exception as e:
            logger.error(f"Failed to create ConfigMap: {e}")
            return False

    def getThreadConfigMap(
        cls, namespace: str, instanceId: str, pipelineRunName: str
    ) -> dict | None:
        """
        Retrieve Slack thread information from a ConfigMap.

        Parameters:
            namespace (str): Kubernetes namespace containing the ConfigMap
            instanceId (str): Unique identifier for the pipeline run (can be None or empty for update pipeline)

        Returns:
            dict | None: Dictionary containing threadId, channelId, pipelineName, and startTime, or None if not found
        """
        try:
            # Load Kubernetes configuration
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()
            # For update pipeline (no instance ID), use "update" as identifier
            instance_identifier = instanceId if instanceId else "update"
            configmap_name = f"slack-thread-{instance_identifier}-{pipelineRunName}"
            configmap = v1.read_namespaced_config_map(
                name=configmap_name, namespace=namespace
            )
            logger.debug(
                f"Retrieved ConfigMap {configmap_name} from namespace {namespace}"
            )
            return configmap.data
        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.debug(
                    f"ConfigMap slack-thread-{instanceId}-{pipelineRunName} not found in namespace {namespace}"
                )
            else:
                logger.error(f"Failed to retrieve ConfigMap: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve ConfigMap: {e}")
            return None

    def updateThreadConfigMap(
        cls, namespace: str, instanceId: str, updates: dict, pipelineRunName: str
    ) -> bool:
        """
        Update the ConfigMap with additional data (e.g., task message timestamps).

        Parameters:
            namespace (str): Kubernetes namespace containing the ConfigMap
            instanceId (str): Unique identifier for the pipeline run (can be None or empty for update pipeline)
            updates (dict): Dictionary of key-value pairs to add/update in the ConfigMap

        Returns:
            bool: True if ConfigMap was updated successfully, False otherwise
        """
        try:
            # Load Kubernetes configuration
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            v1 = client.CoreV1Api()
            # For update pipeline (no instance ID), use "update" as identifier
            instance_identifier = instanceId if instanceId else "update"
            configmap_name = f"slack-thread-{instance_identifier}-{pipelineRunName}"

            # Get existing ConfigMap
            configmap = v1.read_namespaced_config_map(
                name=configmap_name, namespace=namespace
            )

            # Update data
            if configmap.data is None:
                configmap.data = {}
            configmap.data.update(updates)

            # Patch the ConfigMap
            v1.patch_namespaced_config_map(
                name=configmap_name, namespace=namespace, body=configmap
            )
            logger.debug(f"Updated ConfigMap {configmap_name} in namespace {namespace}")
            return True
        except Exception as e:
            logger.error(f"Failed to update ConfigMap: {e}")
            return False

    def deleteThreadConfigMap(
        cls, namespace: str, instanceId: str, pipelineRunName: str
    ) -> bool:
        """
        Delete the ConfigMap containing Slack thread information.

        Parameters:
            namespace (str): Kubernetes namespace containing the ConfigMap
            instanceId (str): Unique identifier for the pipeline run (can be None or empty for update pipeline)
            pipelineRunName (str): Unique identifier for the pipeline run

        Returns:
            bool: True if ConfigMap was deleted successfully, False otherwise
        """
        try:
            # Load Kubernetes configuration
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()

            v1 = client.CoreV1Api()
            # For update pipeline (no instance ID), use "update" as identifier
            instance_identifier = instanceId if instanceId else "update"
            configmap_name = f"slack-thread-{instance_identifier}-{pipelineRunName}"
            v1.delete_namespaced_config_map(name=configmap_name, namespace=namespace)
            logger.info(
                f"Deleted ConfigMap {configmap_name} from namespace {namespace}"
            )
            return True
        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.warning(
                    f"ConfigMap slack-thread-{instanceId}-{pipelineRunName} not found in namespace {namespace}"
                )
            else:
                logger.error(f"Failed to delete ConfigMap: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete ConfigMap: {e}")
            return False
        return {"type": "divider"}


class SlackUtil(metaclass=SlackUtilMeta):
    pass
