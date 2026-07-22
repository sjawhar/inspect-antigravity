from inspect_ai.model import ChatMessage, ChatMessageAssistant, ChatMessageUser


def build_user_prompt(messages: list[ChatMessage]) -> tuple[str, bool]:
    if messages and isinstance(messages[-1], ChatMessageAssistant):
        raise ValueError("Messages input ends with an assistant messages.")

    last_assistant_idx = next(
        (
            i
            for i, message in reversed(list(enumerate(messages)))
            if isinstance(message, ChatMessageAssistant)
        ),
        None,
    )

    has_assistant_response = last_assistant_idx is not None
    start_idx = (last_assistant_idx + 1) if last_assistant_idx is not None else 0
    prompt = "\n\n".join(
        message.text
        for message in messages[start_idx:]
        if isinstance(message, ChatMessageUser)
    )

    return prompt, has_assistant_response
