"""
model_config.example.py
示例模型配置文件。
复制为 model_config.py 后填写真实的 api_key / base_url。
"""

MODELS = [
    {
        "name": "abab6.5-chat",
        "model_id": "abab6.5-chat",
        "api_key": "YOUR_API_KEY",
        "base_url": "https://your-openai-compatible-endpoint/v1",
        "type": "text",
        "enabled": True,
    },
    {
        "name": "qwen3-vl-235b-a22b-instruct",
        "model_id": "qwen3-vl-235b-a22b-instruct",
        "api_key": "YOUR_API_KEY",
        "base_url": "https://your-openai-compatible-endpoint/v1",
        "type": "vision",
        "enabled": True,
    },
    {
        "name": "gemini-2.5-flash",
        "model_id": "gemini-2.5-flash",
        "api_key": "YOUR_API_KEY",
        "base_url": "https://your-openai-compatible-endpoint/v1",
        "type": "vision",
        "enabled": True,
    },
]


def get_enabled_models():
    return [m for m in MODELS if m.get("enabled", True)]


def get_model_by_name(name: str):
    for model in MODELS:
        if model["name"] == name:
            return model
    return None


def get_vision_models():
    return [m for m in MODELS if m.get("type") == "vision" and m.get("enabled", True)]


def get_text_models():
    return [m for m in MODELS if m.get("type") == "text" and m.get("enabled", True)]
