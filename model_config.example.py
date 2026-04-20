"""
model_config.py
独立的模型配置文件，用于其他项目。
配置多个多模态大模型供验证使用。
"""

# ============================================================================
# 模型配置列表
# ============================================================================

MODELS = [
    {
        "name": "glm-5",
        "model_id": "glm-5",
        "api_key": "sk-Ts9NBOV1otAcYr3zxHvdbZnLkMgYJOhqvfLA5uK5Pa99G7N4",
        "base_url": "https://api.shubiaobiao.com/v1",
        "type": "vision",
        "enabled": True,
    },
    {
        "name": "qwen3-vl-235b-a22b-instruct",
        "model_id": "qwen3-vl-235b-a22b-instruct",
        "api_key": "sk-ZBTxddyWe9212sF3iofl8Y89M9SUGHN6RkbylXnTB8aOzJcv",
        "base_url": "https://api.shubiaobiao.com/v1",
        "type": "vision",
        "enabled": True,
    },
    {
        "name": "gemini-2.5-flash",
        "model_id": "gemini-2.5-flash",
        "api_key": "sk-aJwUc1fsxunXrxF0E4qSg0EkObZmOkB5WxBktsKKNSiht1Zt",
        "base_url": "https://api.shubiaobiao.com/v1",
        "type": "vision",
        "enabled": True,
    },
]


# ============================================================================
# 辅助函数
# ============================================================================

def get_enabled_models():
    """获取所有已启用的模型列表。"""
    return [m for m in MODELS if m.get("enabled", True)]


def get_model_by_name(name: str):
    """根据名字获取模型配置。"""
    for m in MODELS:
        if m["name"] == name:
            return m
    return None


def get_vision_models():
    """获取支持视觉的模型列表。"""
    return [m for m in MODELS if m.get("type") == "vision" and m.get("enabled", True)]


def get_text_models():
    """获取纯文本模型列表。"""
    return [m for m in MODELS if m.get("type") == "text" and m.get("enabled", True)]
