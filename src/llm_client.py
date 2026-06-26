import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
MODEL = "Qwen/Qwen2.5-7B-Instruct:together"


def call_llm(
    prompt: str,
    system_prompt: str = None,
    temperature: float = 0.0,
    max_tokens: int = None,
) -> str:
    """
    Send a single prompt to the model and return its text reply.
    """
    client = InferenceClient(
        api_key=os.environ["HF_TOKEN"],
    )
 
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
 
    kwargs = {"model": MODEL, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
 
    completion = client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content