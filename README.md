# typeform-mcp

MCP server per le API Typeform. Espone le principali operazioni Typeform come strumenti MCP utilizzabili da qualsiasi client compatibile con il Model Context Protocol.

## Requisiti

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installato (`pip install uv` oppure `brew install uv`)
- Un [Personal Access Token](https://www.typeform.com/developers/get-started/personal-access-token/) Typeform

## Installazione rapida

Il modo piu semplice per usare il server senza clonare il repo:

```bash
uvx --from git+https://github.com/dscovr/typeform-mcp typeform-mcp
```

Il token deve essere passato tramite variabile d'ambiente:

```bash
TYPEFORM_TOKEN=tfp_... uvx --from git+https://github.com/dscovr/typeform-mcp typeform-mcp
```

## Configurazione MCP

Copia `.mcp.json.example` in `.mcp.json` nella root del tuo progetto e inserisci il tuo token:

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
        "TYPEFORM_TOKEN": "tfp_IL_TUO_TOKEN_PERSONALE"
      }
    }
  }
}
```

**Attenzione:** `.mcp.json` e incluso nel `.gitignore` perche contiene il token in chiaro. Non committarlo mai.

## Sviluppo locale

```bash
# Clona il repo
git clone https://github.com/dscovr/typeform-mcp
cd typeform-mcp

# Installa le dipendenze
uv sync --group dev

# Esegui i test
uv run pytest

# Avvia il server in locale (per test)
TYPEFORM_TOKEN=tfp_... uv run python -m typeform.server
```

Per usare la versione locale come server MCP, aggiorna `.mcp.json`:

```json
{
  "mcpServers": {
    "typeform": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "/percorso/assoluto/typeform-mcp", "typeform-mcp"],
      "env": {
        "TYPEFORM_TOKEN": "tfp_IL_TUO_TOKEN_PERSONALE"
      }
    }
  }
}
```

## Strumenti disponibili

### Form
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_forms` | Elenca tutti i form dell'account |
| `typeform_get_form` | Recupera un form per ID |
| `typeform_create_form` | Crea un nuovo form |
| `typeform_update_form` | Sostituisce un form (PUT) |
| `typeform_patch_form` | Aggiorna campi specifici di un form (PATCH) |
| `typeform_delete_form` | Elimina un form |
| `typeform_duplicate_form` | Duplica un form esistente |
| `typeform_get_messages` | Recupera i messaggi personalizzati di un form |
| `typeform_update_messages` | Aggiorna i messaggi personalizzati di un form |

### Risposte
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_responses` | Elenca le risposte a un form |
| `typeform_delete_responses` | Elimina risposte specifiche |
| `typeform_download_file` | Scarica un file allegato a una risposta |

### Webhook
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_webhooks` | Elenca i webhook di un form |
| `typeform_get_webhook` | Recupera un webhook specifico |
| `typeform_upsert_webhook` | Crea o aggiorna un webhook |
| `typeform_delete_webhook` | Elimina un webhook |

### Temi
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_themes` | Elenca i temi disponibili |
| `typeform_get_theme` | Recupera un tema per ID |
| `typeform_create_theme` | Crea un nuovo tema |
| `typeform_update_theme` | Aggiorna un tema (PUT) |
| `typeform_patch_theme` | Aggiorna campi specifici di un tema (PATCH) |
| `typeform_delete_theme` | Elimina un tema |

### Immagini
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_images` | Elenca le immagini caricate |
| `typeform_get_image` | Recupera un'immagine per ID |
| `typeform_create_image` | Carica una nuova immagine (base64) |
| `typeform_delete_image` | Elimina un'immagine |

### Workspace
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_workspaces` | Elenca i workspace |
| `typeform_get_workspace` | Recupera un workspace per ID |
| `typeform_create_workspace` | Crea un nuovo workspace |
| `typeform_update_workspace` | Aggiorna un workspace |
| `typeform_delete_workspace` | Elimina un workspace |

### Traduzioni
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_list_translations` | Elenca le traduzioni di un form |
| `typeform_update_translation` | Aggiorna una traduzione |
| `typeform_delete_translation` | Elimina una traduzione |
| `typeform_auto_translate` | Attiva la traduzione automatica |

### Account
| Strumento | Descrizione |
|-----------|-------------|
| `typeform_get_account` | Recupera il profilo dell'account corrente |

## Struttura del progetto

```
src/typeform/
    __init__.py     # Export dei tipi principali
    models.py       # Modelli Pydantic per form, campi, logic, ecc.
    client.py       # Client HTTP per le API Typeform
    server.py       # MCP server (entry point)
tests/
    test_client.py  # Test unitari per il client
    test_models.py  # Test unitari per i modelli
```

## Licenza

MIT
