import logging
import sys
from typing import Optional, Dict, Any
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "workflow_id"):
            log_data["workflow_id"] = record.workflow_id
        
        if hasattr(record, "agent"):
            log_data["agent"] = record.agent
        
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        
        return json.dumps(log_data, ensure_ascii=False)


def get_structured_logger(name: str, workflow_id: Optional[str] = None, agent: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    class ContextLogger:
        def __init__(self, base_logger: logging.Logger, workflow_id: Optional[str], agent: Optional[str]):
            self.logger = base_logger
            self.workflow_id = workflow_id
            self.agent = agent
        
        def _add_context(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
            # 提取 extra_data（如果存在）
            extra_data = kwargs.pop("extra_data", None)
            
            # 确保 extra 字典存在
            if "extra" not in kwargs:
                kwargs["extra"] = {}
            
            # 添加上下文信息
            if self.workflow_id:
                kwargs["extra"]["workflow_id"] = self.workflow_id
            if self.agent:
                kwargs["extra"]["agent"] = self.agent
            
            # 将 extra_data 添加到 extra 字典中，这样 StructuredFormatter 可以访问它
            if extra_data is not None:
                kwargs["extra"]["extra_data"] = extra_data
            
            return kwargs
        
        def info(self, msg: str, *args, **kwargs):
            kwargs = self._add_context(kwargs)
            self.logger.info(msg, *args, **kwargs)
        
        def error(self, msg: str, *args, **kwargs):
            kwargs = self._add_context(kwargs)
            self.logger.error(msg, *args, **kwargs)
        
        def warning(self, msg: str, *args, **kwargs):
            kwargs = self._add_context(kwargs)
            self.logger.warning(msg, *args, **kwargs)
        
        def debug(self, msg: str, *args, **kwargs):
            kwargs = self._add_context(kwargs)
            self.logger.debug(msg, *args, **kwargs)
    
    if workflow_id or agent:
        return ContextLogger(logger, workflow_id, agent)
    
    return logger
