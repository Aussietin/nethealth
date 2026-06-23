from rich.console import Console

console = Console()


def print_result(result):
    if result["status"] == "ok":
        console.print(f"[green]✔ {result['name']}[/green]", result)
    else:
        console.print(f"[red]✖ {result['name']}[/red]", result)
