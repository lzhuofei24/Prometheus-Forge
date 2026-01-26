"""
配置加载器模块

使用 Pydantic 加载和管理全局配置（settings.yaml）。
支持通过 MODEL_PRESET 环境变量快速切换模型。
"""

from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import yaml
import os


class ModelConfig(BaseModel):
    """模型配置"""
    name: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"  # 默认使用 DeepSeek-R1-0528-Qwen3-8B
    provider: str = "siliconflow"  # openai、openrouter、siliconflow 等
    temperature: float = 0.7
    max_tokens: int = 8192
    description: Optional[str] = None  # 模型描述
    base_url: Optional[str] = None  # API Base URL
    api_key_env: Optional[str] = None  # API Key 环境变量名
    context_window: Optional[int] = 131072  # 上下文窗口大小（128k）


class PathsConfig(BaseModel):
    """路径配置。小说列表/目录/正文/大纲已来自数据库，workspace 仅供部分遗留逻辑或媒体缓存等使用。"""
    raw_data: str = "./data/raw"
    chroma_db: str = "./data/chroma_db"
    workspace: str = "./workspace"  # 可选；业务数据以 DB 为准


class ChunkingConfig(BaseModel):
    """文本分块配置"""
    chunk_size: int = 1000
    chunk_overlap: int = 200


class Settings(BaseSettings):
    """全局配置类"""
    model_config = {
        "protected_namespaces": ("settings_",),
        "extra": "allow"  # 允许额外字段（用于 model_presets）
    }
    
    model: ModelConfig = Field(default_factory=ModelConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    presets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    agents: Optional[Dict[str, Dict[str, Any]]] = Field(default_factory=dict)
    llm: Optional[Dict[str, Any]] = Field(default_factory=dict)
    media: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    @classmethod
    def load_from_yaml(cls, config_path: Path) -> "Settings":
        """
        从 YAML 文件加载配置
        
        支持通过 MODEL_PRESET 环境变量快速切换模型预设。
        例如：设置 MODEL_PRESET=deepseek_high_temp 来使用高温度预设。
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Settings 实例
        """
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # 加载模型预设
        model_presets = data.get("model_presets", {})
        
        # 检查是否通过环境变量指定了模型预设
        preset_name = os.getenv("MODEL_PRESET")
        if preset_name and preset_name in model_presets:
            # 使用预设配置
            preset_config = model_presets[preset_name]
            model_config = ModelConfig(**preset_config)
        else:
            # 使用默认配置
            model_config = ModelConfig(**data.get("model", {}))
        
        # 构建配置字典
        config_dict = {
            "model": model_config,
            "paths": PathsConfig(**data.get("paths", {})),
                "chunking": ChunkingConfig(**data.get("chunking", {})),
                "presets": model_presets,
                "agents": data.get("agents", {}),
                "llm": data.get("llm", {}),
                "media": data.get("media", {})
        }
        
        # 如果存在新的 llm 配置，优先使用
        if "llm" in data and data["llm"]:
            llm_config = data["llm"]
            model_config.name = llm_config.get("model_name", model_config.name)
            model_config.provider = llm_config.get("provider", model_config.provider)
            model_config.base_url = llm_config.get("base_url", model_config.base_url)
            model_config.api_key_env = llm_config.get("api_key_env", model_config.api_key_env)
            model_config.temperature = llm_config.get("temperature", model_config.temperature)
            model_config.max_tokens = llm_config.get("max_tokens", model_config.max_tokens)
            model_config.context_window = llm_config.get("context_window", model_config.context_window)
        
        instance = cls(**config_dict)
        return instance
    
    def get_available_presets(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有可用的模型预设
        
        Returns:
            模型预设字典
        """
        return self.presets
    
    def switch_model(self, preset_name: str) -> bool:
        """
        切换到指定的模型预设
        
        Args:
            preset_name: 预设名称
            
        Returns:
            是否切换成功
        """
        if preset_name not in self.presets:
            return False
        
        preset_config = self.presets[preset_name]
        self.model = ModelConfig(**preset_config)
        return True
