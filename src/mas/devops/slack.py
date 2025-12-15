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

import logging

logger = logging.getLogger(__name__)


class SlackUtilMeta(type):
    def __init__(cls, *args, **kwargs):
        # Exposed by the client() property method
        cls._client = None

    @property
    def client(cls) -> WebClient:
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

    # Post message to Slack
    # -----------------------------------------------------------------------------
    def postMessageBlocks(cls, channelList: str | list[str], messageBlocks: list, threadId: str = None) -> SlackResponse | list[SlackResponse]:
        responses: list[SlackResponse] = []

        if isinstance(channelList, str):
            channelList = [channelList]
        for channel in channelList:
            try:
                if threadId == "":
                    logger.debug(f"Posting {len(messageBlocks)} block message to {channel} in Slack")
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
                    logger.debug(f"Posting {len(messageBlocks)} block message to {channel} on thread {threadId} in Slack")
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

    def postMessageText(cls, channelList: str | list[str], message: str, attachments=None, threadId: str = None) -> SlackResponse | list[SlackResponse]:
        responses: list[SlackResponse] = []

        if isinstance(channelList, str):
            channelList = [channelList]

        for channel in channelList:
            if threadId == "":
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
                logger.debug(f"Posting message to {channel} on thread {threadId} in Slack")
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
        cls, slackResponse: SlackResponse = None, channelId: str = None, messageTimestamp: str = None, domain: str = "ibm-mas"
    ) -> str:
        if slackResponse is not None:
            channelId = slackResponse["channel"]
            messageTimestamp = slackResponse["ts"]
        elif channelId == "" or messageTimestamp == "":
            raise Exception("Either channelId and messageTimestamp, or slackReponse params must be provided")

        return f"https://{domain}.slack.com/archives/{channelId}/p{messageTimestamp.replace('.', '')}"

    # Edit message in Slack
    # -----------------------------------------------------------------------------
    def updateMessageBlocks(cls, channelName: str, threadId: str, messageBlocks: list) -> SlackResponse:
        logger.debug(f"Updating {len(messageBlocks)} block message in {channelName} on thread {threadId} in Slack")
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

    # Build header block for Slack message
    # -----------------------------------------------------------------------------
    def buildHeader(cls, title: str) -> dict:
        return {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}}

    # Build section block for Slack message
    # -----------------------------------------------------------------------------
    def buildSection(cls, text: str) -> dict:
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    # Build context block for Slack message
    # -----------------------------------------------------------------------------
    def buildContext(cls, texts: list) -> dict:
        elements = []
        for text in texts:
            elements.append({"type": "mrkdwn", "text": text})

        return {"type": "context", "elements": elements}

    # Build divider block for Slack message
    # -----------------------------------------------------------------------------
    def buildDivider(cls) -> dict:
        return {"type": "divider"}


class SlackUtil(metaclass=SlackUtilMeta):
    pass
