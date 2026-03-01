<h1 align="center">Teacher AI</h1>

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
 <a href="https://discord.gg/hUE6T">
    <img src="https://img.shields.io/discord/1346833819172601907?logo=discord&style=flat">


## 🚀 Getting Started

### 🧪 Running Tests

A minimal test suite is provided under `tests/`.
Install the testing dependency and run:

```bash
pip install -r requirements.txt  # includes pytest now
python -m pytest -q
```



1. Clone this repository
   ```bash
   git clone https://github.com/shroroh/TeacherFlow-.git
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up LLM in [`utils/call_llm.py`](./utils/call_llm.py) by providing credentials. To do so, you can put the values in a `.env` file. By default, you can use the AI Studio key with this client for Gemini Pro 2.5 by setting the `GEMINI_API_KEY` environment variable. Alternately, you may supply a project ID (`GEMINI_PROJECT_ID`) and rely on Google Application Default Credentials (ADC). **If ADC are not configured you will see an error like**:

```
google.auth.exceptions.DefaultCredentialsError: Your default credentials were not found.
```

To fix this either:

1. Set `GEMINI_API_KEY` instead of project‑based auth.
2. Run `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS` to
   a service account JSON file as described in
   https://cloud.google.com/docs/authentication/external/set-up-adc

If you want to use another LLM, you can set the `LLM_PROVIDER` environment variable (e.g. `XAI`), and then set the model, url, and API key (e.g. `XAI_MODEL`, `XAI_URL`,`XAI_API_KEY`). If using Ollama, the url is `http://localhost:11434/` and the API key can be omitted.
   You can use your own models. We highly recommend the latest models with thinking capabilities (Claude 3.7 with thinking, O1). You can verify that it is correctly set up by running:
   ```bash
   python utils/call_llm.py

   ИЛИ в среде исполнения, например консоль Power Shell заводим переменные окружения перед запуском основным.
   
   $env:GEMINI_API_KEY="AIzaSyBXEcK_E..|\/..GsWrG"
   $env:GEMINI_MODEL="gemini-flash-latest"
   ```

3. Execute the script (either from root or as a package)
```bash
# legacy entry point kept at project root
python main.py --student-id ivan123 --no-cache

# or use the package namespace
python -m teacherflow --student-id ivan123 --no-cache
```

## Deploy and launch on Colaba service
 ```bash
 https://colab.research.google.com/drive/1fpUQ5kWzyVJ2hIja49_OFr_H8K1F1DZJ?usp=sharing
 ```


<br>
<div align="center">
  <a href="https://youtu.be/AFY67zOpbSo" target="_blank">
    <img src="./assets/youtube_thumbnail.png" width="500" alt="Pocket Flow Codebase Tutorial" style="cursor: pointer;">
  </a>
</div>
<br>



