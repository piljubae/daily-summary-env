import re

_JIRA_KEY = re.compile(r'\b([A-Z]+-\d+)\b', re.IGNORECASE)
_DONE_KW = re.compile(r'완료|done|finish|닫기', re.IGNORECASE)
_CONTINUE_KW = re.compile(r'계속|continue|skip|유지', re.IGNORECASE)
_HANDOFF_KW = re.compile(r'인수인계|handoff|넘김|넘겼', re.IGNORECASE)
_HANDOFF_TARGET = re.compile(r'(?:→|->|에게|께)\s*(.+)', re.IGNORECASE)


def parse_reply(text: str) -> dict | None:
    text = text.strip()
    jira_match = _JIRA_KEY.search(text)
    jira_key = jira_match.group(1).upper() if jira_match else None

    # topic_hint: only when no Jira key — text before the action keyword
    topic_hint = None
    if not jira_key:
        for kw_pat in [_HANDOFF_KW, _DONE_KW, _CONTINUE_KW]:
            m = kw_pat.search(text)
            if m:
                hint = text[:m.start()].strip()
                if hint:
                    topic_hint = hint
                break

    if _HANDOFF_KW.search(text):
        target_match = _HANDOFF_TARGET.search(text)
        to = target_match.group(1).strip() if target_match else ""
        result = {"type": "handoff", "jira_key": jira_key, "to": to, "raw": text}
        if topic_hint is not None:
            result["topic_hint"] = topic_hint
        return result

    if _DONE_KW.search(text):
        result = {"type": "done", "jira_key": jira_key, "raw": text}
        if topic_hint is not None:
            result["topic_hint"] = topic_hint
        return result

    if _CONTINUE_KW.search(text):
        result = {"type": "continue", "jira_key": jira_key, "raw": text}
        if topic_hint is not None:
            result["topic_hint"] = topic_hint
        return result

    return None
