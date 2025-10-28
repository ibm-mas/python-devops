# *****************************************************************************
# Copyright (c) 2025 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

from mas.devops.slack import SlackUtil


def testSendMessage():
    response = SlackUtil.postMessageText("#bot-test", "mas-devops unittest")

    assert "channel" in response.data
    assert response.data["channel"] == "C06453F9KFC"

    assert "ok" in response.data
    assert response.data["ok"] is True

    assert "ts" in response.data
