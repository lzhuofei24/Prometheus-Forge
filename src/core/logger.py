"""
日志模块

使用 colorlog 提供彩色日志输出（如果可用）。
"""

import logging

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False


def setup_logger(name: str = "novel-agent", level: int = logging.INFO) -> logging.Logger:
    """
    设置并返回配置好的日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 创建控制台处理器
    if HAS_COLORLOG:
        handler = colorlog.StreamHandler()
        handler.setLevel(level)
        
        # 设置颜色格式
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)s%(reset)s: %(message)s",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    else:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger
