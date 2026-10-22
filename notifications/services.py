"""Writes for Conversations that aren't sending (sending lives in gateway.py)."""


def mark_read(conversation):
    """Someone opened the chat: the replies are no longer unread."""
    if conversation.unread_count:
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count'])
    return conversation
