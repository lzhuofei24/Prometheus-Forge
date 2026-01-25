"""
LLM 客户端封装模块

提供统一的接口调用 OpenAI 兼容 API（支持 OpenAI、OpenRouter、SiliconFlow 等）。
"""

from typing import Optional, List, Dict, Any
from openai import OpenAI
from openai import APIConnectionError, APIError
import os
import httpx
import ssl
import time
import logging
import redis

logger = logging.getLogger(__name__)


class InvalidResponseError(Exception):
    """API 返回无效响应"""
    pass


class LLMClient:
    """
    LLM 客户端封装类
    
    支持所有 OpenAI 兼容 API（OpenAI、OpenRouter、SiliconFlow 等）。
    """
    
    _cache_service = None
    
    @classmethod
    def set_cache_service(cls, cache_service):
        cls._cache_service = cache_service
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key_env: Optional[str] = None,
        site_url: Optional[str] = None,
        app_name: Optional[str] = None
    ):
        """
        初始化 LLM 客户端
        
        Args:
            provider: 提供商名称（"openai"、"openrouter"、"siliconflow" 等），如果为 None 则从环境变量或默认值读取
            model: 模型名称，如果为 None 则从环境变量或默认值读取
            api_key: API 密钥（如果为 None，从环境变量读取）
            base_url: API 基础 URL（如果为 None，从环境变量或默认值读取）
            temperature: 温度参数（如果为 None，使用默认值）
            max_tokens: 最大 token 数（如果为 None，使用默认值）
            api_key_env: API Key 环境变量名（用于从环境变量读取）
        """
        # 从环境变量读取配置（如果未提供）
        if provider is None:
            provider = os.getenv("DEFAULT_PROVIDER", "openrouter")
        if model is None:
            model = os.getenv("DEFAULT_MODEL", "deepseek/deepseek-chat")
        if temperature is None:
            temp_str = os.getenv("DEFAULT_TEMPERATURE")
            temperature = float(temp_str) if temp_str else 0.7
        
        self.provider = provider
        self.model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        
        # 读取 API Key
        if api_key is None:
            if api_key_env:
                api_key = os.getenv(api_key_env)
            elif provider == "siliconflow":
                api_key = os.getenv("SILICONFLOW_API_KEY")
            elif provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY")
            else:
                api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError(f"API Key 未设置！请设置环境变量: {api_key_env or 'OPENROUTER_API_KEY'}")
        
        self.api_key = api_key
        
        # 读取 Base URL
        if base_url is None:
            base_url = os.getenv("OPENAI_API_BASE")
        
        # 根据 provider 设置默认 base_url
        if base_url is None:
            if provider == "siliconflow":
                base_url = "https://api.siliconflow.cn/v1"
            elif provider == "openrouter":
                base_url = "https://openrouter.ai/api/v1"
            elif provider == "openai":
                base_url = "https://api.openai.com/v1"
        
        self.base_url = base_url
        
        # OpenRouter 需要的 header
        default_headers = {}
        if provider == "openrouter":
            default_headers["HTTP-Referer"] = site_url or os.getenv("OPENROUTER_SITE_URL", "http://localhost")
            default_headers["X-Title"] = app_name or os.getenv("OPENROUTER_APP_NAME", "Novel-Agent")
        
        # 配置 HTTP 客户端
        http_client = httpx.Client(
            timeout=1200.0,
            verify=True,
        )
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            default_headers=default_headers if default_headers else None
        )
        
        # 初始化 Redis 连接（用于统计）
        try:
            self.redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=0,
                decode_responses=True,
                socket_connect_timeout=2
            )
            # 测试连接
            self.redis_client.ping()
            logger.info("Redis 统计连接成功")
        except Exception as e:
            logger.warning(f"Redis 统计连接失败（统计功能将不可用）: {e}")
            self.redis_client = None
        
        logger.info(f"已初始化 LLM 客户端: provider={provider}, model={model}, base_url={base_url}")
    
    def switch_model(self, model: str, provider: Optional[str] = None, base_url: Optional[str] = None) -> None:
        """
        动态切换模型
        
        Args:
            model: 新的模型名称
            provider: 新的提供商（如果为 None，保持当前提供商）
            base_url: 新的 Base URL（如果为 None，使用默认值）
        """
        self.model = model
        if provider is not None:
            self.provider = provider
        
        if base_url is None:
            if self.provider == "siliconflow":
                base_url = "https://api.siliconflow.cn/v1"
            elif self.provider == "openrouter":
                base_url = "https://openrouter.ai/api/v1"
            elif self.provider == "openai":
                base_url = "https://api.openai.com/v1"
            else:
                base_url = self.base_url
        
        self.base_url = base_url
        
        default_headers = {}
        if self.provider == "openrouter":
            default_headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
            default_headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "Novel-Agent")
        
        http_client = httpx.Client(timeout=1200.0, verify=True)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            http_client=http_client,
            default_headers=default_headers if default_headers else None
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 8,
        retry_delay: float = 1.0
    ) -> str:
        """
        发送聊天请求（带重试机制）
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数（如果为 None，使用默认值）
            max_tokens: 最大 token 数（如果为 None，使用默认值）
            extra_headers: 额外的 HTTP 头部（OpenRouter 需要）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            
        Returns:
            AI 回复的文本内容
        """
        # 使用默认值（如果未提供）
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        if extra_headers is not None:
            kwargs["extra_headers"] = extra_headers
        
        if LLMClient._cache_service:
            cached = LLMClient._cache_service.get_llm_response(messages, temperature)
            if cached:
                logger.debug("LLM response cache hit")
                return cached
        
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                
                # 防御性检查：确保响应有效
                if not response:
                    raise InvalidResponseError("API 返回空响应 (response is None)")
                if not response.choices:
                    raise InvalidResponseError(f"API 返回无效响应 (choices为空): {response}")
                if not response.choices[0].message:
                    raise InvalidResponseError(f"API 返回无效消息 (message为空): {response}")
                if response.choices[0].message.content is None:
                    raise InvalidResponseError(f"API 返回空内容 (content is None): finish_reason={response.choices[0].finish_reason}")
                
                # 统计 Token 消耗（不影响主业务流程）
                try:
                    if self.redis_client and hasattr(response, 'usage') and response.usage:
                        pipe = self.redis_client.pipeline()
                        pipe.incr("stats:api_calls")
                        pipe.incrbyfloat("stats:prompt_tokens", float(response.usage.prompt_tokens))
                        pipe.incrbyfloat("stats:completion_tokens", float(response.usage.completion_tokens))
                        pipe.execute()
                        logger.info(f"📊 统计已记录: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
                    else:
                        logger.warning(f"⚠️ 统计跳过: redis={bool(self.redis_client)}, has_usage={hasattr(response, 'usage')}, usage={getattr(response, 'usage', None)}")
                except Exception as e:
                    logger.warning(f"❌ 统计记录失败（不影响主业务）: {e}")
                
                content = response.choices[0].message.content
                if LLMClient._cache_service:
                    LLMClient._cache_service.set_llm_response(messages, content, temperature)
                return content
            except (APIConnectionError, APIError, httpx.HTTPError, ssl.SSLError, OSError, InvalidResponseError) as e:
                last_error = e
                error_msg = str(e)
                if hasattr(e, 'response') and hasattr(e.response, 'text'):
                    try:
                        error_msg = e.response.text
                    except:
                        pass
                
                logger.warning(f"API 调用失败 (尝试 {attempt}/{max_retries}): {error_msg}")
                
                if attempt < max_retries:
                    try:
                        http_client = httpx.Client(timeout=60.0, verify=True)
                        self.client = OpenAI(
                            api_key=self.api_key,
                            base_url=self.base_url,
                            http_client=http_client
                        )
                    except Exception:
                        pass
                    delay = retry_delay * (2 ** (attempt - 1))
                    if delay > 20.0:
                        delay = 20.0
                    time.sleep(delay)
                else:
                    raise Exception(f"API 请求失败: {error_msg}") from e
        
        raise last_error
