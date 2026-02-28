"""
Templates module for Gatekeeper Evolve MCP state files.

Provides Jinja2 templates for:
- verifier_loop.md.j2: YAML frontmatter with session metadata
- token_secret.j2: Token with TEST_CMD_B64 and TEST_CMD_HASH
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Get the directory where templates are stored
TEMPLATES_DIR = Path(__file__).parent

# Create Jinja2 environment with FileSystemLoader
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=False,
    lstrip_blocks=False,
)


def get_template(name: str):
    """
    Get a template by name.

    Args:
        name: The template filename (e.g., 'verifier_loop.md.j2')

    Returns:
        A Jinja2 Template object ready for rendering
    """
    return env.get_template(name)
