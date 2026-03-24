import json

from rich.console import Console
from rich.panel import Panel

from forge.compiler.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from forge.compiler.schema import ProductionPlan


class VisionCompiler:
    def __init__(self, client, model: str = "gpt-4o"):
        self.client = client
        self.model = model
        self.console = Console()

    async def compile(self, story: str, num_scenes: int = 6) -> ProductionPlan:
        user_prompt = USER_PROMPT_TEMPLATE.format(story=story, num_scenes=num_scenes)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        plan = ProductionPlan(**data)

        # Validate and auto-fix DAG
        from forge.scheduler.dag_validator import validate_and_fix
        report = validate_and_fix(plan)
        if report.issues:
            for issue in report.issues:
                tag = "[red]ERROR[/red]" if issue.level == "error" else "[yellow]WARN[/yellow]"
                fixed = " (auto-fixed)" if issue.auto_fixed else ""
                self.console.print(f"  {tag} [{issue.rule}] {issue.message}{fixed}")
        if report.has_errors:
            raise ValueError(f"DAG validation failed: {report.summary()}")

        # Summary
        total_duration = sum(s.estimated_duration_sec for s in plan.scenes)
        self.console.print(
            Panel(
                f"[bold]Title:[/bold] {plan.title}\n"
                f"[bold]Scenes:[/bold] {len(plan.scenes)}\n"
                f"[bold]Assets:[/bold] {len(plan.assets)}\n"
                f"[bold]Estimated total duration:[/bold] {total_duration:.0f}s",
                title="[green]Production Plan Compiled[/green]",
            )
        )

        return plan
