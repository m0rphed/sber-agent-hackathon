from collections.abc import Callable
import json
from typing import Any

from rich import print as rprint
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel

console = Console()


def log_api_response(name_method_function: str, url: str, params: dict | None = None) -> Callable:
    """
    Декоратор для логирования API ответов
    """

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # показываем имя функции и URL
            console.rule(f'[bold cyan]📡 API Call: {name_method_function}[/bold cyan]')
            rprint(f'[dim]URL:[/dim] {url}')
            if params or kwargs:
                rprint(f'[dim]Params:[/dim] {params or kwargs}')
            result = await func(self, *args, **kwargs)
            return result

        return wrapper

    return decorator


# декоратор для rich принта входа и выхода любой асинхронной функции
# с любым количеством аргументов
def print_in_out(func: Callable) -> Callable:
    async def wrapper(*args, **kwargs) -> None:
        result = await func(*args, **kwargs)
        rprint('input args:', f'[yellow]{args}[/yellow]')
        rprint('input kwargs:', f'[bold]{kwargs}[/bold]')
        rprint('result:', result)

    return wrapper


def _log_json(title: str, data: Any, style: str = 'green') -> None:
    """
    Логирование JSON с rich форматированием
    """
    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    panel = Panel(
        RichJSON(json_str),
        title=f'[bold {style}]{title}[/bold {style}]',
        border_style=style,
        expand=False,
    )
    console.print(panel)


def _log_error(title: str, message: str) -> None:
    """
    Логирует ошибку
    """
    console.print(f'[bold red]- Error! {title}:[/bold red] {message}')


def _log_info(message: str) -> None:
    """
    Логирует информационное сообщение
    """
    console.print(f'[dim]- Info: {message}[/dim]')
