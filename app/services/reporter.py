import os
from jinja2 import Environment, FileSystemLoader
from typing import List, Any
from dataclasses import dataclass

@dataclass
class BoardItem:
    number: int
    title: str
    url: str
    updated_at: str
    metadata: Any  # IssueMetadata

class Reporter:
    """Generates static HTML reports."""
    
    def __init__(self, template_dir: str = "app/templates"):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        
    def generate_board(self, items: List[BoardItem], output_path: str = "job_board.html", site_url: str = "") -> str:
        """Render the Job Board HTML."""
        template = self.env.get_template("board.html")
        html = template.render(issues=items, site_url=site_url)
        
        with open(output_path, "w") as f:
            f.write(html)
            
        return os.path.abspath(output_path)

    def generate_feed(self, items: List[BoardItem], output_path: str = "feed.xml", site_url: str = "") -> str:
        """Render the Atom Feed."""
        from datetime import datetime
        
        template = self.env.get_template("feed.xml")
        html = template.render(
            issues=items,
            now=datetime.utcnow().isoformat() + "Z",
            site_url=site_url
        )
        
        with open(output_path, "w") as f:
            f.write(html)
            
        return os.path.abspath(output_path)
