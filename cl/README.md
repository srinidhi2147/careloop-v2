# CareLoop

A voice-first medicine assistant for elderly people and their families.

The elder talks to CareLoop: "What do I need to take?", "I took it", "I need help". The caregiver watches every dose update live on a dashboard, gets an alert if a dose is missed or help is requested, and builds the schedule by uploading a photo of a prescription.

Built for the **NVIDIA x Nebius Global AI Hackathon** (track: Best Apps and Agents).

## How it uses NVIDIA and Nebius

| Part | What it does | Model / service |
| --- | --- | --- |
| Prescription reading | Reads a photo of a prescription and returns medicines, strengths, frequency and notes as JSON | **NVIDIA Nemotron 3.5 Super VL** (`nvidia/Nemotron-3.5-Super-VL`) on **Nebius Token Factory** |
| Daily summary | Writes a calm summary of the day's doses for the caregiver | Same model, same endpoint |
| Voice tools | Schedule, log a dose, skip, agenda, ask for help | MCP server at `/mcp` (Streamable HTTP) |

Token Factory is used through its OpenAI-compatible API, so there is no extra SDK beyond `openai`. The vision-language model let us read a prescription photo and write plain-language text with one model and one key.

## Safety by design

- **The caregiver confirms everything.** The AI never writes to the care plan by itself. Rows it is unsure about (low confidence, missing name, no clock time) are highlighted, and the caregiver edits and approves each line before saving.
- **It never guesses.** The prompt tells the model to leave unreadable fields empty instead of inventing a medicine name.
- **Dose times are validated** before saving (`HH:MM`, 24-hour).
- **Not medical advice.** CareLoop logs and reminds. It does not recommend medicines or doses.
- Use sample prescriptions only. Do not upload real patient data.

## How it works

```
Elder (voice in the browser, or any MCP client such as Alexa+)
        |
        v
   FastAPI backend  <---- Caregiver dashboard (live over SSE)
   + MCP server /mcp            |
        |                       +-- prescription photo --> Nemotron 3.5 Super VL
        v                                                   (Nebius Token Factory)
     SQLite care plan
```

- Voice in the browser uses the Web Speech API (speech recognition and speech synthesis). It works in Chrome and Edge. In Chrome, the audio is processed by the browser vendor's speech service, so a fully private setup would use an on-device speech model instead.
- The same actions are exposed as MCP tools at `/mcp`, so Alexa+ or any other MCP client can call them. Connecting a real Alexa+ add-on additionally needs a public HTTPS URL and OIDC authentication, which this demo does not include.

## Run it

Requirements: Python 3.10 or newer, and a Nebius Token Factory API key.

```bash
git clone <your-repo-url>
cd careloop
pip install -e ".[dev]"
cp .env.example .env        # Windows: copy .env.example .env
# edit .env and set NEBIUS_API_KEY
uvicorn careloop.main:create --factory --port 8000 --env-file .env
```

Open http://localhost:8000.

### Without an API key (offline demo)

```bash
# macOS / Linux / Git Bash
USE_MOCK_AI=1 uvicorn careloop.main:create --factory --port 8000
```

```powershell
# Windows PowerShell
$env:USE_MOCK_AI="1"
uvicorn careloop.main:create --factory --port 8000
```

```bat
:: Windows Command Prompt
set USE_MOCK_AI=1
uvicorn careloop.main:create --factory --port 8000
```

In mock mode, the prescription upload always returns the same sample prescription.

### Settings (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEBIUS_API_KEY` | (empty) | Your Token Factory key. Never commit it. |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.us-north1.nebius.com/v1/` | Use the URL shown for your account in the Token Factory console |
| `NEBIUS_MODEL_ID` | `nvidia/Nemotron-3.5-Super-VL` | Any vision-capable Nemotron model on Token Factory |
| `USE_MOCK_AI` | `0` | `1` = offline sample data, no API calls |
| `SEED_DEMO` | `1` | `0` = start with an empty care plan |
| `CARELOOP_DB` | `careloop.db` | SQLite file path |
| `CARELOOP_TZ` | `Asia/Kolkata` | Time zone for dose times |
| `GRACE_MINUTES` | `60` | Minutes before a dose counts as late |
| `AUTO_MISSED` | `0` | `1` = mark late doses as missed automatically |
| `MAX_UPLOAD_BYTES` | `5000000` | Upload size limit |
| `MCP_ALLOWED_HOSTS` | (empty) | Comma-separated host allow-list for `/mcp` in production |

### Tests

```bash
pytest
```

## Try the demo flow

1. Start with `SEED_DEMO=0` for an empty care plan.
2. Upload a photo of a sample prescription and click **Read prescription**.
3. Check the highlighted rows, fix any times, and click **Save to care plan**.
4. Tap **Speak** and say "What do I need to take?", then "I took it".
5. Watch the dashboard update live. Say "I need help" to raise an alert.
6. Click **Write daily summary** to get the Nemotron-written summary.

## Known limits

- Prescription reading works on photos (PNG, JPEG, WEBP). PDFs are not supported.
- Handwriting and low-quality photos give uncertain rows. This is why the caregiver review step exists.
- Voice input needs Chrome or Edge and microphone permission.
- Single household, no login. Add authentication before real use.

## Feedback on the platform

See [FRICTION_LOG.md](FRICTION_LOG.md).

## License

MIT. See [LICENSE](LICENSE).