import importlib.util
from pathlib import Path
from typing import Dict, List


ROLE_DEFAULTS = {
    "primary_reviewer": "glm-5",
    "peer_reviewer": "gemini-2.5-flash",
    "final_judge": "qwen3-vl-235b-a22b-instruct",
}


def _load_model_config_module() -> object:
    config_path = Path(__file__).resolve().parents[3] / "model_config.py"
    spec = importlib.util.spec_from_file_location("local_model_config", str(config_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 model_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_models() -> List[Dict[str, object]]:
    module = _load_model_config_module()
    return list(getattr(module, "MODELS", []))


def load_model_roles() -> Dict[str, Dict[str, object]]:
    models = {item["name"]: item for item in load_models()}
    resolved: Dict[str, Dict[str, object]] = {}
    for role, model_name in ROLE_DEFAULTS.items():
        if model_name not in models:
            raise KeyError("模型角色 %s 对应的模型 %s 不存在" % (role, model_name))
        resolved[role] = models[model_name]
    return resolved
