# typeform-mcp

MCP server for the Typeform API. Exposes Typeform operations as MCP tools usable from any client that supports the Model Context Protocol.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed (`pip install uv` or `brew install uv`)
- A Typeform [Personal Access Token](https://www.typeform.com/developers/get-started/personal-access-token/)

## Quick install

The easiest way to use the server without cloning the repo:

```bash
TYPEFORM_TOKEN=tfp_... uvx --from git+https://github.com/dscovr/typeform-mcp typeform-mcp
```

## MCP configuration

Copy `.mcp.json.example` to `.mcp.json` in the root of your project and fill in your token:

```json
{
  "mcpServers": {
    "typeform": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/dscovr/typeform-mcp",
        "typeform-mcp"
      ],
      "env": {
        "TYPEFORM_TOKEN": "tfp_YOUR_PERSONAL_TOKEN"
      }
    }
  }
}
```

**Note:** `.mcp.json` is listed in `.gitignore` because it contains your token in plain text. Never commit it.

## Local development

```bash
# Clone the repo
git clone https://github.com/dscovr/typeform-mcp
cd typeform-mcp

# Install dependencies
uv sync --group dev

# Run tests
uv run pytest

# Start the server locally
TYPEFORM_TOKEN=tfp_... uv run python -m typeform.server
```

To use a local build as your MCP server, update `.mcp.json`:

```json
{
  "mcpServers": {
    "typeform": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "/absolute/path/to/typeform-mcp", "typeform-mcp"],
      "env": {
        "TYPEFORM_TOKEN": "tfp_YOUR_PERSONAL_TOKEN"
      }
    }
  }
}
```

## Available tools

### Forms
| Tool | Description |
|------|-------------|
| `typeform_list_forms` | List all forms in the account |
| `typeform_get_form` | Get a form by ID |
| `typeform_create_form` | Create a new form |
| `typeform_update_form` | Replace a form (PUT) |
| `typeform_patch_form` | Partially update a form (PATCH) |
| `typeform_delete_form` | Delete a form |
| `typeform_duplicate_form` | Duplicate an existing form |
| `typeform_get_messages` | Get custom messages for a form |
| `typeform_update_messages` | Update custom messages for a form |

### Responses
| Tool | Description |
|------|-------------|
| `typeform_list_responses` | List responses for a form |
| `typeform_export_responses_csv` | Export all responses as CSV |
| `typeform_delete_responses` | Delete specific responses |
| `typeform_download_file` | Download a file attached to a response |

### Webhooks
| Tool | Description |
|------|-------------|
| `typeform_list_webhooks` | List webhooks for a form |
| `typeform_get_webhook` | Get a specific webhook |
| `typeform_upsert_webhook` | Create or update a webhook |
| `typeform_delete_webhook` | Delete a webhook |

### Themes
| Tool | Description |
|------|-------------|
| `typeform_list_themes` | List available themes |
| `typeform_get_theme` | Get a theme by ID |
| `typeform_create_theme` | Create a new theme |
| `typeform_update_theme` | Replace a theme (PUT) |
| `typeform_patch_theme` | Partially update a theme (PATCH) |
| `typeform_delete_theme` | Delete a theme |

### Images
| Tool | Description |
|------|-------------|
| `typeform_list_images` | List uploaded images |
| `typeform_get_image` | Get an image by ID |
| `typeform_create_image` | Upload a new image (base64) |
| `typeform_delete_image` | Delete an image |

### Workspaces
| Tool | Description |
|------|-------------|
| `typeform_list_workspaces` | List workspaces |
| `typeform_get_workspace` | Get a workspace by ID |
| `typeform_create_workspace` | Create a new workspace |
| `typeform_update_workspace` | Rename a workspace |
| `typeform_delete_workspace` | Delete a workspace |

### Translations
| Tool | Description |
|------|-------------|
| `typeform_list_translations` | List translations for a form |
| `typeform_get_translation_statuses` | Get translation statuses |
| `typeform_update_translation` | Update a translation |
| `typeform_delete_translation` | Delete a translation |
| `typeform_auto_translate` | Trigger automatic translation |

### Account
| Tool | Description |
|------|-------------|
| `typeform_get_account` | Get the current account profile |

## Project structure

```
src/typeform/
    __init__.py     # Public type exports
    models.py       # Pydantic models for forms, fields, logic, etc.
    client.py       # HTTP client for the Typeform API
    server.py       # MCP server entry point
tests/
    test_client.py  # Unit tests for the client
    test_models.py  # Unit tests for the models
```

## License

MIT
