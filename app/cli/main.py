import asyncio
import typer
from typing import Annotated
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.json import JSON

from app.services.extractor import ExtractorService
from app.services.triage import TriageService
from app.models.schemas import IssueMetadata

app = typer.Typer(help="GitHub Issue Triage Automation CLI")
console = Console()

@app.command()
def extract(file: str = typer.Argument(..., help="Path to text file containing the issue body")):
    """
    Debug Mode: Run ONLY the Extractor Service on a file.
    """
    if not file:
        console.print("[red]Error: file path required[/red]")
        raise typer.Exit(code=1)

    with console.status("Initialising LLM..."):
        try:
            extractor = ExtractorService()
        except ValueError as e:
            console.print(f"[red]Setup Error: {e}[/red]")
            raise typer.Exit(code=1)

    try:
        with open(file, "r") as f:
            text = f.read()
    except FileNotFoundError:
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Extracting metadata from {len(text)} chars...[/bold blue]")
    
    try:
        metadata = asyncio.run(extractor.extract(text))
    except Exception as e:
        console.print(f"[red]Extraction Failed: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(Panel(JSON(metadata.model_dump_json()), title="Extracted Metadata", border_style="green"))


@app.command()
def decide(
    file: str = typer.Argument(..., help="Path to text file containing the issue body"),
    rules: str = typer.Option("rules.yaml", help="Path to rules configuration")
):
    """
    Debug Mode: Run Extractor -> Rules Engine.
    """
    with console.status("Initialising Services..."):
        try:
            extractor = ExtractorService()
            triage = TriageService(rules)
        except ValueError as e:
            console.print(f"[red]Setup Error: {e}[/red]")
            raise typer.Exit(code=1)

    try:
        with open(file, "r") as f:
            text = f.read()
    except FileNotFoundError:
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(code=1)

    console.print("[bold blue]Step 1: Extractor[/bold blue]")
    try:
        metadata = asyncio.run(extractor.extract(text))
    except Exception as e:
        console.print(f"[red]Extraction Failed: {e}[/red]")
        raise typer.Exit(code=1)
    
    console.print(f"  Confidence: {metadata.extraction_confidence}")

    console.print("[bold blue]Step 2: Rules Engine[/bold blue]")
    action = triage.evaluate(metadata)

    table = Table(title="Triage Decision")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Priority", str(action.priority_score))
    table.add_row("Labels", ", ".join(action.labels))
    table.add_row("Reasoning", action.reasoning)

    console.print(table)


@app.command()
def scan(
    repo: Annotated[str, typer.Argument(help="Repository in format 'owner/repo'")],
    issue: Annotated[int, typer.Argument(help="Issue ID to triage")],
    role: Annotated[str, typer.Option(help="Filter by persona: 'maintainer' (P4-P5), 'contributor' (P1-P2), or 'all'")] = "all",
    rules: Annotated[str, typer.Option(help="Path to rules configuration")] = "rules.yaml",
    apply: Annotated[bool, typer.Option("--apply", help="Actually apply labels and comments to GitHub")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False
):
    """
    Universal Interface: Scan an issue and filter by persona (Maintainer vs Contributor).
    """
    from app.services.github_service import GitHubService
    from app.core.config import settings

    # 1. Setup
    with console.status("Initialising..."):
        try:
            gh = GitHubService(github_token=settings.GITHUB_TOKEN)
            extractor = ExtractorService()
            triage = TriageService(rules)
        except Exception as e:
            console.print(f"[red]Setup Error: {e}[/red]")
            raise typer.Exit(code=1)

        if "/" not in repo:
             console.print("[red]Repo must be 'owner/repo'[/red]")
             raise typer.Exit(code=1)
        owner, repo_name = repo.split("/")

    # 2. Fetch
    try:
        with console.status(f"Fetching issue {repo}#{issue}..."):
            gh_issue = asyncio.run(gh.fetch_issue(owner, repo_name, issue))
    except Exception as e:
        console.print(f"[red]Fetch Failed: {e}[/red]")
        raise typer.Exit(code=1)

    # 3. Extract
    text_content = f"Title: {gh_issue.title}\n\nBody:\n{gh_issue.body}\n\nComments:\n" + "\n".join(gh_issue.comments)
    
    with console.status("Analysing..."):
        metadata = asyncio.run(extractor.extract(text_content))

    # 4. Decide
    action = triage.evaluate(metadata)
    priority = action.priority_score

    # 5. Filter Logic
    visible = True
    if role == "maintainer" and priority < 4:
        visible = False
        console.print(f"[dim]Skipping Issue #{issue} (Priority {priority}): Not a Maintainer target (P4+)[/dim]")
    elif role == "contributor" and priority > 2:
        visible = False
        console.print(f"[dim]Skipping Issue #{issue} (Priority {priority}): Not a Contributor target (P1-P2)[/dim]")

    if not visible:
        raise typer.Exit(0)

    # 6. Report
    console.print(Panel(f"Analysis for {repo}#{issue} ({role.upper()} View)", style="bold green"))
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric")
    table.add_column("Result")
    
    table.add_row("Summary", metadata.summary)
    table.add_row("Difficulty", metadata.difficulty)
    table.add_row("Skills", ", ".join(metadata.required_skills))
    table.add_row("Priority", str(priority))
    table.add_row("Labels", ", ".join(action.labels))
    
    console.print(table)
    console.print(f"[italic]{action.reasoning}[/italic]")

    # 7. Apply
    if apply:
        if not yes:
            confirm = typer.confirm("Do you want to apply these changes to GitHub?")
            if not confirm:
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit()
        
        with console.status("Applying to GitHub..."):
            success = asyncio.run(gh.apply_labels(owner, repo_name, issue, action.labels))
            
            if success:
                console.print("[bold green]✔ Labels applied![/bold green]")
            else:
                console.print("[bold red]✘ Failed to apply changes.[/bold red]")
    else:
        console.print("\n[dim]Dry run complete. Use --apply to execute changes.[/dim]")

@app.command()
def report(
    repo: Annotated[str, typer.Argument(help="Repository 'owner/repo'")],
    limit: int = typer.Option(5, help="Number of issues to scan"),
    delay: float = typer.Option(0.0, help="Delay (in seconds) between requests to avoid Rate Limiting")
):
    """
    Generate the 'Contributor Job Board' (Static HTML).
    Scans recent issues and creates a filtered report.
    """
    from app.services.github_service import GitHubService
    from app.services.reporter import Reporter, BoardItem
    from app.core.config import settings

    # Wrap everything in a single async function
    async def run_batch():
        # 1. Fetch
        with console.status(f"Fetching last {limit} issues from {repo}..."):
            gh = GitHubService(github_token=settings.GITHUB_TOKEN)
            extractor = ExtractorService()
            triage = TriageService("rules.yaml")
            
            if "/" not in repo:
                 console.print("[red]Repo must be 'owner/repo'[/red]")
                 raise typer.Exit(code=1)
            owner, repo_name = repo.split("/")
            
            try:
                issues = await gh.fetch_issues(owner, repo_name, limit=limit)
            except Exception as e:
                console.print(f"[red]Fetch Failed: {e}[/red]")
                return

            console.print(f"[blue]Found {len(issues)} open issues.[/blue]")

        # 2. Analyze
        async def analyze_issue(issue):
            text = f"{issue.title}\n{issue.body}"
            try:
                meta = await extractor.extract(text)
                action = triage.evaluate(meta)
                return (issue, meta, action)
            except Exception:
                return None

        with console.status(f"Batch Analysing (AI)... Delay: {delay}s"):
            if delay > 0:
                results = []
                for i in issues:
                    res = await analyze_issue(i)
                    results.append(res)
                    await asyncio.sleep(delay)
            else:
                tasks = [analyze_issue(i) for i in issues]
                if not tasks:
                    console.print("[yellow]No issues to analyze.[/yellow]")
                    return
                results = await asyncio.gather(*tasks)

        # 3. Filter & Assemble
        board_items = []
        for res in results:
            if not res: continue
            issue, meta, action = res
            
            # Filter: Only P1 or P2 (Contributor Focused)
            if action.priority_score <= 2:
                board_items.append(BoardItem(
                    number=issue.number,
                    title=issue.title,
                    url=issue.url,
                    updated_at=issue.updated_at,
                    metadata=meta
                ))

        # 4. Generate
        if not board_items:
            console.print("[yellow]No 'Good First Issues' found in this batch.[/yellow]")
            return

        reporter = Reporter()
        path = reporter.generate_board(board_items)
        
        # Generate Feed
        site_url = f"https://github.com/{owner}/{repo_name}"
        feed_path = reporter.generate_feed(board_items, site_url=site_url)

        console.print(f"[bold green]✔ Job Board Generated: {path}[/bold green]")
        console.print(f"[bold green]✔ RSS Feed Generated: {feed_path}[/bold green]")
        console.print(f"  Includes {len(board_items)} opportunities.")

    # Run the async main
    asyncio.run(run_batch())



@app.command()
def action(
    apply: bool = typer.Option(True, help="Apply changes (default True for Actions)"),
):
    """
    GitHub Action Entrypoint.
    Automatically detects context from GITHUB_EVENT_PATH and configuration from repo.
    """
    import os
    import json
    from app.services.github_service import GitHubService
    from app.core.config import settings
    
    console.print("[bold blue]🚀 Starting AI Triage Action[/bold blue]")

    # 1. Detect Context
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        console.print("[red]Error: GITHUB_EVENT_PATH not found. Are we running in an Action?[/red]")
        raise typer.Exit(code=1)
        
    with open(event_path, "r") as f:
        event = json.load(f)
        
    # Extract Issue details
    # Matches 'issues' event or 'issue_comment' event
    issue_data = event.get("issue")
    if not issue_data:
        console.print("[yellow]No issue object found in event. Skipping.[/yellow]")
        raise typer.Exit(0)
        
    issue_number = issue_data["number"]
    repo_full = os.getenv("GITHUB_REPOSITORY") # "owner/repo"
    
    if not repo_full:
        console.print("[red]GITHUB_REPOSITORY missing.[/red]")
        raise typer.Exit(code=1)
        
    owner, repo_name = repo_full.split("/")
    
    console.print(f"Target: [cyan]{owner}/{repo_name}#{issue_number}[/cyan]")

    # 2. "Polite Guest" Configuration Strategy
    # Look for user config in multiple locations
    # Look for user config in multiple locations
    if os.path.exists(".github/issueops.yaml"):
        console.print("[green]Found config: .github/issueops.yaml[/green]")
        rules_file = ".github/issueops.yaml"
    elif os.path.exists(".github/triage.yaml"):
        console.print("[yellow]Found legacy config: .github/triage.yaml (Please rename to issueops.yaml)[/yellow]")
        rules_file = ".github/triage.yaml"
    elif os.path.exists("rules.yaml"):
        # Fallback to local default (bundled in container)
        console.print("[dim]Using default rules.yaml[/dim]")
        rules_file = "rules.yaml"
    else:
        console.print("[red]No rules configuration found![/red]")
        raise typer.Exit(code=1)

    # 3. Execution
    # Reuse the logic by calling the service components directly
    # (We can't easily call the other CLI commands, so we duplicate the simple flow)
    
    with console.status("Running Triage Pipeline..."):
        try:
            gh = GitHubService(github_token=settings.GITHUB_TOKEN)
            extractor = ExtractorService()
            triage = TriageService(rules_file)
            
            # Fetch
            gh_issue = asyncio.run(gh.fetch_issue(owner, repo_name, issue_number))
            
            # --- DUPLICATE CHECK ---
            from app.services.duplicate_service import DuplicateService
            dupe_service = DuplicateService(gh, extractor)
            
            dupe_result = asyncio.run(dupe_service.check_duplicate(owner, repo_name, gh_issue.title, gh_issue.body, gh_issue.number))
            
            if dupe_result.confidence >= 0.9 and dupe_result.duplicate_number:
                console.print(f"[bold red]DUPLICATE DETECTED:[/bold red] #{dupe_result.duplicate_number}")
                console.print(f"Reason: {dupe_result.reasoning}")
                
                if apply:
                    msg = f"Marking as duplicate of #{dupe_result.duplicate_number}.\nLogic: {dupe_result.reasoning}"
                    asyncio.run(gh.post_comment(owner, repo_name, issue_number, msg))
                    asyncio.run(gh.apply_labels(owner, repo_name, issue_number, ["duplicate"]))
                else:
                    console.print(f"[dim][DRY RUN] Would comment 'Duplicate of #{dupe_result.duplicate_number}' and label as 'duplicate'[/dim]")
                return

            if 0.7 <= dupe_result.confidence < 0.9 and dupe_result.duplicate_number:
                 if apply:
                     msg = f"Possible duplicate of #{dupe_result.duplicate_number} (Confidence: {dupe_result.confidence:.2f}). Please check."
                     asyncio.run(gh.post_comment(owner, repo_name, issue_number, msg))
                 else:
                     console.print(f"[dim][DRY RUN] Would comment 'Possible duplicate of #{dupe_result.duplicate_number}'[/dim]")
            # -----------------------

            # Extract
            text = f"{gh_issue.title}\n{gh_issue.body}\n" + "\n".join(gh_issue.comments)
            meta = asyncio.run(extractor.extract(text))
            
            # Decide
            action_result = triage.evaluate(meta)
            
        except Exception as e:
            console.print(f"[red]Pipeline Failed: {e}[/red]")
            raise typer.Exit(code=1)

    # 4. Report
    console.print(Panel(f"Decision: P{action_result.priority_score}", title="AI Triage Result", style="green"))
    console.print(f"Labels: {', '.join(action_result.labels)}")
    console.print(f"Reason: {action_result.reasoning}")

    # 5. Apply
    if apply:
        with console.status("Applying to GitHub..."):
            success = asyncio.run(gh.apply_labels(owner, repo_name, issue_number, action_result.labels))
            if success:
                console.print("[bold green]✔ Labels applied[/bold green]")
            else:
                console.print("[bold red]✘ Failed to apply labels[/bold red]")
                raise typer.Exit(code=1)

@app.command()
def audit(
    repo: Annotated[str, typer.Argument(help="Repository 'owner/repo'")],
    limit: int = typer.Option(10, help="Number of issues to scan")
):
    """
    Generate a CSV for manual accuracy auditing.
    Columns: ID, Title, AI_Difficulty, AI_Priority, Human_Review_Col
    """
    import csv
    from app.services.github_service import GitHubService
    from app.core.config import settings

    # Async Logic
    async def run_audit():
        with console.status(f"Fetching {limit} issues from {repo}..."):
            gh = GitHubService(github_token=settings.GITHUB_TOKEN)
            extractor = ExtractorService()
            triage = TriageService("rules.yaml")
            
            if "/" not in repo:
                 console.print("[red]Repo must be 'owner/repo'[/red]")
                 raise typer.Exit(code=1)
            owner, repo_name = repo.split("/")
            
            issues = await gh.fetch_issues(owner, repo_name, limit=limit)
            console.print(f"[blue]Found {len(issues)} issues. analyzing...[/blue]")

        results = []
        with console.status("Analysing..."):
            for issue in issues:
                text = f"{issue.title}\n{issue.body}"
                try:
                    meta = await extractor.extract(text)
                    action = triage.evaluate(meta)
                    results.append({
                        "id": issue.number,
                        "title": issue.title,
                        "ai_difficulty": meta.difficulty,
                        "ai_priority": action.priority_score,
                        "ai_skills": ", ".join(meta.required_skills),
                        "human_difficulty": "",  # For user to fill
                        "human_priority": "",    # For user to fill
                        "notes": ""
                    })
                except Exception as e:
                    console.print(f"[red]Error on #{issue.number}: {e}[/red]")

        # Write CSV
        filename = f"audit_{owner}_{repo_name}.csv"
        with open(filename, "w", newline="") as csvfile:
            fieldnames = ["id", "title", "ai_difficulty", "ai_priority", "ai_skills", "human_difficulty", "human_priority", "notes"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for r in results:
                writer.writerow(r)
                
        console.print(f"[bold green]✔ Audit CSV generated: {filename}[/bold green]")
        console.print("Open this file to compare AI predictions vs Reality.")

    asyncio.run(run_audit())

if __name__ == "__main__":
    app()
