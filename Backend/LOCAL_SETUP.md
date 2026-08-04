# Run NEXA Locally

The language model and speech recognition run locally. The LangGraph agent can
use public web search when a request needs live information or when it must
discover an official website URL.

## 1. Create the local configuration

The included .env uses OpenRouter as the primary chat model, a second
OpenRouter model as fallback, and LM Studio as the final local fallback. Keep
the LM Studio and Stable Diffusion URLs on 127.0.0.1; the application rejects
non-local LM Studio language-model servers.

For OpenRouter, add your key to `.env`:

```env
LLM_PROVIDER="openrouter_lmstudio"
OPENROUTER_MODEL="google/gemma-4-26b-a4b-it:free"
OPENROUTER_FALLBACK_MODEL="poolside/laguna-s-2.1:free"
OPENROUTER_API_KEY="..."
```

`openrouter_lmstudio` tries Gemma on OpenRouter first, then Laguna on
OpenRouter with the same API key, then LM Studio if both remote models are
unavailable. Use `openrouter` to disable the local fallback, or `lmstudio` to
run only the local model.

## 2. Install Python packages

Run: `..\.venv\Scripts\python.exe -m pip install -r Requirements.txt` from `Backend`.

## 3. Start LM Studio fallback

1. Install LM Studio and download the Qwen 3.5 2B GGUF Q4 model. If it does not
   run comfortably, use Qwen3 1.7B GGUF Q4_K_M.
2. Load the model.
3. In Developer, start the local server on port 1234.
4. Put the loaded model identifier in LMSTUDIO_MODEL in .env.

When `LLM_PROVIDER` is `openrouter_lmstudio`, the LangGraph brain sends model
and tool-selection requests to OpenRouter first. It tries
`google/gemma-4-26b-a4b-it:free`, then `poolside/laguna-s-2.1:free`, then
retries through the OpenAI-compatible LM Studio endpoint at
`http://127.0.0.1:1234/v1` if both remote models fail.

## 3a. Build the owner resume RAG index

The owner profile questions use embeddings over `Resume_Yashraj.pdf`.

1. In LM Studio, download and load an embedding model such as
   `nomic-ai/nomic-embed-text-v1.5`.
2. Keep the local server running at `http://127.0.0.1:1234/v1`.
3. Set `EMBEDDING_MODEL` in `.env` to the loaded embedding model id.
4. Build the vector index:

   `python -m Backend.OwnerRAG build --force`

This creates `Backend/Data/OwnerRAG/index.json`, which stores resume chunks and their
embedding vectors. Owner/creator questions automatically use this index.

## 4. Add offline voice recognition

Download and unzip the Vosk small English model into
models/vosk-model-small-en-us-0.15.

For another language, download that language's Vosk model and update
INPUT_LANGUAGE and VOSK_MODEL_PATH in .env. Vosk runs entirely on-device.

If Windows cannot open the default microphone, set VOSK_INPUT_DEVICE to a
working device index after checking the available devices on that computer.

## 5. Optional local image generation

Install and start AUTOMATIC1111 Stable Diffusion WebUI with:
webui-user.bat --api

It must listen at http://127.0.0.1:7860. On this 8 GB Intel Iris Xe laptop,
start with 512x512, 15 steps, and batch size 1, as configured in .env.
Image generation may be slow and can use substantial system memory.

## 6. Google Workspace connections

Nexa supports per-browser OAuth connections to Gmail, Google Calendar, and
Google Drive. Each browser authorizes its own Google account; access and refresh
tokens are encrypted in `Backend/Data/GoogleConnections.json` and are never sent to the
frontend.

Gmail sending uses the Gmail API and the account connected in Nexa. No Gmail
password, app password, or SMTP configuration is used. Drafting does not send
anything. An explicit send request creates the existing confirmation card, and
the message is delivered only after **Send email** is clicked.

Google Drive is strictly read-only. Calendar reads run directly; creating,
updating, deleting, or responding to an event is held for UI approval.

1. Install the dependencies:

   `python -m pip install -r Backend/Requirements.txt`

2. In Google Cloud, create an OAuth **Web application** client and add this
   authorized redirect URI for local development:

   `http://localhost:8000/api/google/oauth/callback`

3. Enable the Gmail API, Google Drive API, and Google Calendar API for your
   Cloud project. Nexa connects to those first-party APIs directly; no Google
   MCP API enrollment is needed.
4. Configure the OAuth consent screen and add yourself as a test user.
5. Add the client ID and client secret to `.env`:

   ```env
   GOOGLE_OAUTH_CLIENT_ID="...apps.googleusercontent.com"
   GOOGLE_OAUTH_CLIENT_SECRET="..."
   GOOGLE_OAUTH_REDIRECT_URI="http://localhost:8000/api/google/oauth/callback"
   GOOGLE_TOKEN_ENCRYPTION_KEY="..."
   ```

   Generate the last value once with:

   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

6. Restart `python -m Backend.WebApp`, then use the **Connect** buttons in Nexa’s
   Connected Apps panel. Google will open a consent screen for each service.

Nexa uses first-party Google API connectors. Connected-app actions that can
change external state are intercepted for UI approval before they execute.

For a public deployment, change `GOOGLE_OAUTH_REDIRECT_URI` to your HTTPS
domain callback, add that exact URI to the Google OAuth client, and set
`GOOGLE_OAUTH_COOKIE_SECURE="true"`.

## 7. Geoapify places and directions

Nexa can find nearby places, resolve addresses, and calculate driving, walking,
or bicycle routes through Geoapify. Create a Geoapify API key and add it to
`.env`:

```env
GEOAPIFY_API_KEY="..."
```

Restart Nexa after saving the key. For a request such as “find restaurants near
me”, the browser asks for location permission and sends the resulting
coordinates only with that request. If permission is denied, ask with a city,
address, or neighbourhood instead. Geoapify is intentionally used only for
read-only location data; its place results do not provide dependable venue
photos or crowd ratings.

## React voice-chat application

1. Add `OPENROUTER_API_KEY` in `.env`. Start LM Studio too if you want fallback,
   load the model configured in `.env`, and start its local server.
2. Install Python dependencies: `pip install -r Backend/Requirements.txt`
3. Build the frontend once: `cd "Jarvis Frontend"` then `npm install` and `npm run build`
4. From the project root, run: `.venv\Scripts\python.exe -m Backend.Main` (or
   `.venv\Scripts\python.exe -m Backend.WebApp`). Direct launches also self-correct to
   the project environment when `.venv` exists.
5. Open `http://127.0.0.1:8000`

For frontend development, run `npm run dev` in `Jarvis Frontend`. Its example
environment file points the Vite app at the local NEXA API.

## Agent flow

Each request enters a LangGraph `Brain -> Tools -> Brain` loop. The model can
answer normally, search the live web, open an exact website URL, control an
installed application, change volume, manage tasks, draft emails, send Gmail
messages, create a local document, or use configured MCP tools from connected
services. Tool results are returned to the brain
before it writes the final response. The React UI receives safe planning and
tool progress plus answer tokens over the existing SSE endpoint; it never
receives private model chain-of-thought.
