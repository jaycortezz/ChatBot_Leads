"""Fingerprint known chatbot/live-chat widgets in a page's HTML.

Detection is signature-based: each vendor injects a recognizable script tag,
iframe src, or JS call into the page. This catches widgets that load
synchronously in the initial HTML. Some chatbots inject via a tag manager and
won't be visible in raw HTML - false negatives are possible, but false
positives are rare because the signatures are vendor-specific domains.
"""

# vendor label -> substrings that appear in HTML when their widget is embedded
CHATBOT_SIGNATURES = {
    "Intercom": ["widget.intercom.io", "intercomcdn.com", "intercom('boot'"],
    "Drift": ["js.driftt.com", "drift.load("],
    "Tidio": ["code.tidio.co"],
    "HubSpot Chat": ["js.hs-scripts.com", "js.hsforms.net", "hs-chat"],
    "Zendesk Chat": ["zdassets.com", "zopim.com"],
    "Tawk.to": ["embed.tawk.to"],
    "LiveChat": ["cdn.livechatinc.com"],
    "Crisp": ["client.crisp.chat"],
    "Facebook Messenger": ["connect.facebook.net", "fb-customer-chat"],
    "Freshchat": ["wchat.freshchat.com", "freshchat.com/js"],
    "Gorgias": ["config.gorgias.chat"],
    "Kommunicate": ["widget.kommunicate.io"],
    "Landbot": ["landbot.io/v3"],
    "Voiceflow": ["cdn.voiceflow.com"],
    "ManyChat": ["widget.manychat.com"],
    "Chatbot.com": ["widget-v3.chatbot.com", "widget.chatbot.com"],
    "Ada": ["static.ada.support"],
    "Podium": ["connect.podium.com"],
    "Birdeye": ["birdeye.com/webchat"],
}


def detect_chatbot(html: str) -> dict:
    """Return {'detected': bool, 'vendor': str} for already-fetched page HTML."""
    if not html:
        return {"detected": False, "vendor": ""}

    lowered = html.lower()
    for vendor, signatures in CHATBOT_SIGNATURES.items():
        for sig in signatures:
            if sig.lower() in lowered:
                return {"detected": True, "vendor": vendor}

    return {"detected": False, "vendor": ""}
